"""Seed a fresh database with 20 basic Ingredients.

An operator-run side script, never wired into the app lifespan or entrypoint.sh: seeding
stays an explicit step, the same way Alembic migrations are. Run it after
`docker compose up` has started the backend at least once, so the bootstrap Admin exists.

    cd backend && uv run python scripts/seed_ingredients.py

Every Ingredient goes in through InventoryService.create_ingredient, the same path
POST /inventory/ingredients takes, so name uniqueness, validation, and logging behave
exactly as they do for a Warehouse Manager working through the UI. Re-running is safe:
an Ingredient whose name already exists is skipped, and only the missing ones are added.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# The script lives one directory below the backend root, so `container`, `services`, and the
# rest of the flat backend layout are only importable once that root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from constants import SETTINGS  # noqa: E402
from container import Container  # noqa: E402
from data_models import CreateIngredientRequest, Unit, User, UserRole  # noqa: E402
from exceptions import DuplicateIngredientNameError  # noqa: E402
from utils import load_config  # noqa: E402

# Opening stock is set directly at creation, matching what POST /inventory/ingredients does
# with a caller-supplied current_stock. No opening `purchase` Stock Movement is recorded, so
# the append-only audit trail starts empty and every later row in it describes a real event.
# "Salmon Fillet" and "Heavy Cream" deliberately start below their own thresholds, so the
# Low-Stock Alerts screen has something to show on a freshly seeded database.
INGREDIENTS: tuple[CreateIngredientRequest, ...] = (
    CreateIngredientRequest(name="Tomato", unit=Unit.kg, current_stock=Decimal("40"), min_stock_threshold=Decimal("10")),
    CreateIngredientRequest(name="Onion", unit=Unit.kg, current_stock=Decimal("35"), min_stock_threshold=Decimal("8")),
    CreateIngredientRequest(name="Potato", unit=Unit.kg, current_stock=Decimal("50"), min_stock_threshold=Decimal("12")),
    CreateIngredientRequest(name="Carrot", unit=Unit.kg, current_stock=Decimal("20"), min_stock_threshold=Decimal("5")),
    CreateIngredientRequest(name="Garlic", unit=Unit.kg, current_stock=Decimal("6"), min_stock_threshold=Decimal("2")),
    CreateIngredientRequest(name="Mushroom", unit=Unit.kg, current_stock=Decimal("12"), min_stock_threshold=Decimal("4")),
    CreateIngredientRequest(name="Chicken Breast", unit=Unit.kg, current_stock=Decimal("25"), min_stock_threshold=Decimal("8")),
    CreateIngredientRequest(name="Ground Beef", unit=Unit.kg, current_stock=Decimal("18"), min_stock_threshold=Decimal("6")),
    CreateIngredientRequest(name="Salmon Fillet", unit=Unit.kg, current_stock=Decimal("3"), min_stock_threshold=Decimal("5")),
    CreateIngredientRequest(name="Rice", unit=Unit.kg, current_stock=Decimal("30"), min_stock_threshold=Decimal("10")),
    CreateIngredientRequest(name="Pasta", unit=Unit.kg, current_stock=Decimal("28"), min_stock_threshold=Decimal("10")),
    CreateIngredientRequest(name="Flour", unit=Unit.kg, current_stock=Decimal("45"), min_stock_threshold=Decimal("10")),
    CreateIngredientRequest(name="Sugar", unit=Unit.kg, current_stock=Decimal("22"), min_stock_threshold=Decimal("6")),
    CreateIngredientRequest(name="Salt", unit=Unit.kg, current_stock=Decimal("15"), min_stock_threshold=Decimal("3")),
    CreateIngredientRequest(name="Butter", unit=Unit.kg, current_stock=Decimal("10"), min_stock_threshold=Decimal("4")),
    CreateIngredientRequest(name="Cheese", unit=Unit.kg, current_stock=Decimal("14"), min_stock_threshold=Decimal("5")),
    CreateIngredientRequest(name="Olive Oil", unit=Unit.liter, current_stock=Decimal("25"), min_stock_threshold=Decimal("8")),
    CreateIngredientRequest(name="Milk", unit=Unit.liter, current_stock=Decimal("20"), min_stock_threshold=Decimal("6")),
    CreateIngredientRequest(name="Heavy Cream", unit=Unit.liter, current_stock=Decimal("2"), min_stock_threshold=Decimal("4")),
    CreateIngredientRequest(name="Egg", unit=Unit.piece, current_stock=Decimal("200"), min_stock_threshold=Decimal("40")),
)


async def _resolve_actor(db: AsyncSession) -> User:
    """Find the Admin the seeded Ingredients are attributed to.

    The first active Admin by id, which on a fresh stack is the account
    `main._bootstrap_first_admin` creates. Used for logging and for
    `InventoryService.create_ingredient`'s own actor argument, nothing is written
    against this User's own row.

    Args:
        db: The active database session.

    Returns:
        The first active Admin User.

    Raises:
        SystemExit: If no active Admin exists yet.
    """
    result = await db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active.is_(True)).order_by(User.id).limit(1)
    )
    actor = result.scalar_one_or_none()
    if actor is None:
        raise SystemExit(
            "No active Admin found. Start the backend once against this database so the "
            "bootstrap Admin is created (BOOTSTRAP_ADMIN must not be false), then re-run this script."
        )
    return actor


async def seed(container: Container) -> tuple[int, int]:
    """Create every Ingredient in INGREDIENTS that does not already exist.

    Args:
        container: The initialized DI container, read for its database resource and
            its InventoryService provider.

    Returns:
        A tuple of (created, skipped) counts.
    """
    logger = container.logging()
    # Awaited, unlike logger above: inventory_service depends on realtime_service, which
    # depends on the async connection_registry Resource, so its provider returns an awaitable
    # rather than the service itself. The synchronous logging Resource does not.
    inventory_service = await container.inventory_service()
    database = await container.database()

    created = 0
    skipped = 0
    async with database.session_factory() as db:
        actor = await _resolve_actor(db)
        for payload in INGREDIENTS:
            try:
                await inventory_service.create_ingredient(db, actor, payload)
            except DuplicateIngredientNameError:
                # create_ingredient rolls back its own failed transaction before raising, so
                # the session stays usable for the rest of the loop.
                logger.info("Ingredient already exists, skipping: name={}", payload.name)
                skipped += 1
            else:
                created += 1
    return created, skipped


async def main() -> None:
    """Build the DI container, run the seed, and release the container's resources.

    The container is built here rather than imported from `main`, which would wire every
    API module and construct a FastAPI app this script has no use for.

    Returns:
        Nothing.
    """
    container = Container()
    container.config.from_dict(load_config(SETTINGS.CONFIG_PATH))
    await container.init_resources()
    try:
        created, skipped = await seed(container)
        container.logging().info("Seed complete: created={} skipped={}", created, skipped)
    finally:
        await container.shutdown_resources()


if __name__ == "__main__":
    asyncio.run(main())

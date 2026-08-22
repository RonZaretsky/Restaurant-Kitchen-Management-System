import sys
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass

from dependency_injector import containers, providers
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from clients.llm import LLMClient
from clients.websocket import ConnectionRegistry
from services.ai_service import AIService
from services.auth_service import AuthService
from services.inventory_service import InventoryService
from services.kitchen_service import KitchenService
from services.menu_service import MenuService
from services.order_service import OrderService
from services.realtime_service import RealtimeService
from services.table_service import TableService
from services.user_service import UserService


@dataclass
class Database:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def _init_logging(level: str, colorize: bool, format: str) -> Generator:
    logger.remove()
    logger.add(sys.stdout, colorize=colorize, level=level.upper(), format=format)
    yield logger
    logger.remove()


async def _init_database(host: str, port: int, user: str, password: str, name: str) -> AsyncGenerator[Database, None]:
    url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield Database(engine=engine, session_factory=factory)
    await engine.dispose()


async def _init_connection_registry(logger) -> AsyncGenerator[ConnectionRegistry, None]:
    registry = ConnectionRegistry(logger=logger)
    yield registry
    await registry.close_all()


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    logging = providers.Resource(
        _init_logging,
        level=config.logging.level,
        colorize=config.logging.colorize,
        format=config.logging.format,
    )

    database = providers.Resource(
        _init_database,
        host=config.database.host,
        port=config.database.port,
        user=config.database.user,
        password=config.database.password,
        name=config.database.name,
    )

    auth_service = providers.Factory(
        AuthService,
        secret_key=config.auth.secret_key,
        token_expiry_hours=config.auth.token_expiry_hours,
        logger=logging,
    )

    user_service = providers.Factory(
        UserService,
        logger=logging,
    )

    menu_service = providers.Factory(
        MenuService,
        logger=logging,
    )

    table_service = providers.Factory(
        TableService,
        logger=logging,
    )

    connection_registry = providers.Resource(_init_connection_registry, logger=logging)

    realtime_service = providers.Factory(
        RealtimeService,
        registry=connection_registry,
        logger=logging,
    )

    # No trap-23 ordering constraint: kitchen_service takes no realtime_service (or any other
    # provider) dependency, it only reads. Grouped here, next to order_service, since both are
    # the orders/kitchen domain rather than for any ordering requirement.
    kitchen_service = providers.Factory(
        KitchenService,
        logger=logging,
    )

    # inventory_service must stay below realtime_service, and (since Story 5.2) order_service
    # must stay below inventory_service: these are plain Python class-body assignments evaluated
    # top to bottom, so injecting a not-yet-defined provider into one declared above it raises
    # NameError at import time. Any future provider that depends on another must be declared
    # after it, the same way.
    inventory_service = providers.Factory(
        InventoryService,
        logger=logging,
        realtime_service=realtime_service,
    )

    # Depends on inventory_service (Story 5.2, pick_up_item's atomic stock deduction), so must be
    # declared below it.
    order_service = providers.Factory(
        OrderService,
        logger=logging,
        realtime_service=realtime_service,
        inventory_service=inventory_service,
    )

    # Story 6.1: the first external-service client (AD-12). Singleton, not Factory: the
    # underlying AsyncOpenAI client is safely reusable across requests, no need to reconstruct it
    # per-injection the way a stateless Factory-built service is. No trap-23 ordering constraint
    # of its own — llm_client depends only on config, not on another provider.
    llm_client = providers.Singleton(
        LLMClient,
        api_key=config.smart_chef.api_key,
        model=config.smart_chef.model,
    )

    # Singleton, not Factory (a deliberate deviation from every other service in this container):
    # AD-14's "reject a second concurrent generation for the same Cook" guard lives in an
    # in-process set on the AIService instance itself (see its own docstring). A Factory would
    # hand each injected request a fresh, empty set, silently defeating the guard the first time
    # two different requests each got their own instance — the opposite of RealtimeService's own
    # shared-state pattern, where the state lives in a separately-injected Resource
    # (connection_registry) rather than the Factory-built service itself; here, since AIService
    # has no other per-request state to keep separate, making the whole service a Singleton is
    # the simpler equivalent. Depends on llm_client, so must be declared below it (trap 23).
    ai_service = providers.Singleton(
        AIService,
        logger=logging,
        llm_client=llm_client,
    )

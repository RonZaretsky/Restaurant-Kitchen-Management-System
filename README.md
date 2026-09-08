# Restaurant Kitchen Management System

A full-stack application for managing restaurant kitchen operations.

---

## Project Structure

```
.
├── backend/          # FastAPI Python server
├── frontend/         # React TypeScript client
└── docker-compose.yml
```

---

## Run everything with Docker Compose

### Before the first run: configure Smart Chef

The AI features (recipe suggestions and the Smart Assistant chat) call the OpenAI API, so they
need an API key. Compose reads it from `backend/.env`, which is not part of the repository.
Create it by duplicating the example file:

```bash
cp backend/.env.example backend/.env
```

Then open `backend/.env` and fill in the two Smart Chef values:

```env
OPENAI_API_KEY=sk-...      # your own OpenAI API key
OPENAI_MODEL=gpt-4o-mini   # any chat-capable model; this is the default
```

Do this **before** `docker compose up`, since the file is read when the backend container starts.
The same file also holds `JWT_SECRET_KEY`, which is worth setting for the same reason.

Skipping this step is not fatal. The stack still builds and runs, and every screen except Smart
Chef behaves normally. What happens instead is that the backend logs a warning at startup and
each Smart Chef request fails with `OPENAI_API_KEY is not configured`. Add the key and restart
the stack to turn the feature on.

### Start the stack

```bash
docker compose up --build
```

That single command brings up all three services: PostgreSQL, the backend, and the frontend.
The backend waits for Postgres to report healthy, applies any pending Alembic migrations, and
only then starts the API, so there is no separate migration step to run.

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

Compose publishes Postgres on 5432. If that port is already taken by a native Postgres install,
stop it before starting the stack:

```bash
sudo launchctl unload /Library/LaunchDaemons/postgresql-16.plist   # macOS
```

### First login

A fresh database has no accounts. On its first startup against an empty `users` table, the
backend automatically creates a default Admin:

| Username | Password |
|---|---|
| `admin` | `admin` |

Sign in with these, then immediately create a real Admin account and change or retire this one
from the Users screen. Set `BOOTSTRAP_ADMIN=false` in `backend/.env` to disable this behavior.

### Optional: seed sample ingredients

A fresh database also has no ingredients, so the inventory, recipe, and stock-deduction screens
start empty. `backend/scripts/seed_ingredients.py` fills them with 20 basic ingredients (produce,
proteins, staples, dairy) at sensible stock levels. Two of them are seeded below their own minimum
threshold on purpose, so the low-stock alerts screen has something to show.

Run it after the stack is up and the backend has started at least once, since the script
attributes what it creates to the bootstrap Admin:

```bash
# Inside the running backend container
docker compose exec backend uv run --no-dev python scripts/seed_ingredients.py

# Or from the host, against the Postgres published on 5432
cd backend && uv run python scripts/seed_ingredients.py
```

Each ingredient is created through the same service the `POST /inventory/ingredients` endpoint
uses, so names, units, and thresholds are validated exactly as they would be from the Inventory
screen. Re-running is safe: an ingredient whose name already exists is skipped rather than
duplicated or overwritten, and the run reports `created=<n> skipped=<n>` when it finishes.

The script is never run automatically. Seeding stays an explicit choice, the way migrations are
an explicit step in the container entrypoint.

---

## Backend

Built with **FastAPI**, **dependency-injector**, and **loguru**. Configuration is loaded from `backend/config.yaml` and can be overridden with environment variables.

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Run locally

```bash
cd backend

# Install dependencies
uv sync

# Set up secrets (required: without it the app uses a publicly known JWT key
# and warns at startup that every session is forgeable)
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET_KEY

# (Optional) copy and edit config
cp config.yaml config.yaml   # edit host, port, log level, etc.

# Apply database migrations (required: the app no longer creates the schema itself)
uv run alembic upgrade head

# Start the server
uv run python main.py

# (Optional) seed 20 basic ingredients, once the server has run at least once
uv run python scripts/seed_ingredients.py
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### Run with Docker

```bash
cd backend
docker build -t kitchen-backend .
docker run -p 8000:8000 kitchen-backend
```

### Configuration

Edit `backend/config.yaml`:

```yaml
app:
  debug: false

server:
  host: "0.0.0.0"
  port: 8000

logging:
  level: "INFO"
  colorize: true
  format: "..."
```

---

## Frontend

Built with **React 19**, **TypeScript**, and **Vite**. Uses **pnpm** as the package manager.

### Requirements

- Node.js 20+
- [pnpm](https://pnpm.io/installation)

### Run locally

```bash
cd frontend

# Install dependencies
pnpm install

# Configure backend connection
cp .env.example .env
# Edit .env and set VITE_API_BASE_URL if your backend runs on a different address

# Start the dev server
pnpm dev
```

The app will be available at `http://localhost:3000`.

### Run with Docker

```bash
cd frontend
docker build -t kitchen-frontend .
docker run -p 80:80 kitchen-frontend
```

### Configuration

Copy `.env.example` to `.env` and adjust the values:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT_MS=5000
```

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API base URL |
| `VITE_API_TIMEOUT_MS` | `5000` | Request timeout in milliseconds |

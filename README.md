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

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

### First login

A fresh database has no accounts. On its first startup against an empty `users` table, the
backend automatically creates a default Admin:

| Username | Password |
|---|---|
| `admin` | `admin` |

Sign in with these, then immediately create a real Admin account and change or retire this one
from the Users screen. Set `BOOTSTRAP_ADMIN=false` in `backend/.env` to disable this behavior.

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

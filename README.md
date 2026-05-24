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

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

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

# (Optional) copy and edit config
cp config.yaml config.yaml   # edit host, port, log level, etc.

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

# 🔮 The Clusterizer

The Clusterizer pulls Jira issues that match a JQL query, generates embeddings with Ollama, groups them with K-Means, and returns labeled clusters through a FastAPI API and a Vite frontend.

| Layer | Technology |
|---|---|
| Frontend | Vanilla TypeScript with Vite |
| Backend | Python + FastAPI |
| Embeddings | Ollama `/api/embed` |
| Cluster labels | Ollama `/api/generate` |
| Clustering | scikit-learn K-Means |
| Database | PostgreSQL 18 + [pgvector](https://github.com/pgvector/pgvector) |

---

## How it works

1. You submit a Jira base URL, optional username/email, an API token or PAT, a JQL filter, and a maximum cluster count.
2. The API creates an analysis record, returns immediately, and runs the analysis pipeline in a background task.
3. Jira issues are fetched from `/rest/api/3/search`, with automatic fallback to `/rest/api/2/search`.
4. Each issue is embedded from its summary plus the first 500 characters of its description.
5. K-Means tries cluster counts from `2` up to `min(requested_clusters, ticket_count)` and keeps the best silhouette score, so the requested value acts as a ceiling instead of a forced exact split.
6. Ollama generates a short label for each cluster. If that fails, the backend falls back to keyword extraction.
7. Results are stored in PostgreSQL, and the frontend polls every 3 seconds to render percentages, keywords, and representative tickets.

Notes:

- API tokens and PATs are passed to the background task and are not stored in the database.
- Analyses move through `pending`, `running`, `completed`, and `failed` states.
- Jira fetches are capped at 1000 issues per analysis.

---

## Quick start with Podman Compose

```bash
git clone https://github.com/macel94/the-clusterizer.git
cd the-clusterizer
podman compose up --build
```

That same command works from the devcontainer terminal too. The devcontainer installs
`podman-compose` and wraps `podman` to the rootful engine inside the privileged
container, which avoids the nested rootless `newuidmap` failure.

If you previously ran an older Postgres image for this repo, remove the stale named volume once before restarting so Compose can initialize the PostgreSQL 18 layout cleanly:

```bash
podman volume rm the-clusterizer_postgres_data
```

This starts the local development stack:

| Service | Purpose | URL |
|---|---|---|
| Frontend | nginx reverse proxy to the Vite dev server | http://localhost:3000 |
| Backend API | FastAPI | http://localhost:8000 |
| API docs | Swagger UI | http://localhost:8000/docs |
| Ollama | Embeddings + label generation | http://localhost:11434 |
| PostgreSQL | Application database | localhost:5432 |

On the first boot, Compose also runs `ollama-model-pull`, which downloads the configured embedding and LLM models into the shared Ollama volume. Analyses will not succeed until those models are available.

---

## Configuration

Backend settings are read from environment variables or `backend/.env`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://clusterizer:clusterizer@localhost:5432/clusterizer` | SQLAlchemy connection string |
| `OLLAMA_URL` | `http://localhost:11434` | Base URL for Ollama |
| `OLLAMA_EMBED_MODEL` | `embeddinggemma` | Model used for `/api/embed` |
| `OLLAMA_EMBED_DIM` | `768` | Embedding dimension; must match the embedding model |
| `OLLAMA_LLM_MODEL` | `gemma4:e4b` | Model used for `/api/generate` |

Common embedding dimensions:

- `embeddinggemma` -> `768`
- `nomic-embed-text` -> `768`
- `mxbai-embed-large` -> `1024`

---

## Dev Containers

The repo includes `.devcontainer/devcontainer.json` for local Dev Containers.

The shared workspace setting in `.vscode/settings.json` points the Dev Containers extension at `podman` for this repository, so `Reopen in Container` uses Podman by default as long as `podman` is on your `PATH`.

- Base image: Ubuntu 24.04
- Tooling: Python 3.12, Node.js 24
- Post-create setup installs `podman-compose`, creates rootful `podman` wrappers in `/usr/local/bin`, creates `backend/.venv`, installs `backend/requirements.txt` and `backend/requirements-test.txt`, and runs `npm install` in `frontend`
- Forwarded ports: `3000`, `8000`, `11434`, `5432`, `5433`, `18080`

The devcontainer is a full development environment. You can run the application
stack from its integrated terminal with `podman compose up --build`, and the nested
Podman storage is persisted in the `the-clusterizer-podman-storage` volume so images
and named volumes survive devcontainer rebuilds.

---

## Local development

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 18 with the `pgvector` extension
- Ollama with the models you want to use
- Podman with a compose provider, if you want to run the local app or test stacks with containers

Docker is no longer required for the supported local devcontainer and GitHub CI workflow.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt

export DATABASE_URL=postgresql://clusterizer:clusterizer@localhost:5432/clusterizer
export OLLAMA_URL=http://localhost:11434
export OLLAMA_EMBED_MODEL=embeddinggemma
export OLLAMA_EMBED_DIM=768
export OLLAMA_LLM_MODEL=gemma4:e4b

uvicorn app.main:app --reload
```

If you already ran analyses with a different embedding model, delete or rerun
those analyses after switching defaults. Semantic search should compare queries
against embeddings produced by the same model family.

On startup, the backend creates its tables and runs `CREATE EXTENSION IF NOT EXISTS vector`, so the configured PostgreSQL user must be allowed to create that extension.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

When you run the Vite dev server directly, it listens on http://localhost:5173.
For standalone frontend development, set `VITE_API_BASE=http://localhost:8000` before starting it so `/api` requests go straight to the backend.

With the compose stack, open http://localhost:3000 instead.
That port is served by nginx, which proxies frontend assets to the internal Vite server on `frontend:5173` and `/api` requests to the backend.

---

## Authentication

| Jira flavor | Username field | Token field |
|---|---|---|
| Cloud | Email address | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Server / Data Center | Leave blank | Personal Access Token sent as Bearer auth |

If `username` is present, the backend uses HTTP basic auth. If it is omitted, the backend sends `Authorization: Bearer <pat>`.

---

## JQL examples

```sql
project = "OPS" AND status != Done
project in ("PLATFORM", "INFRA") AND created >= -30d
issuetype = Bug AND priority in (High, Critical) AND status != Closed
```

---

## API reference

### `POST /api/analyses`

Starts a new analysis.

```json
{
  "jira_url": "https://your-domain.atlassian.net",
  "username": "user@example.com",
  "pat": "your-token",
  "jql_filter": "project = TEST",
  "num_clusters": 5
}
```

Rules:

- `username` is optional
- `num_clusters` must be between `2` and `20` and is treated as the maximum number of clusters to consider

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/analyses` | List analyses ordered by newest first |
| `GET` | `/api/analyses/{id}` | Get one analysis, including cluster results when complete |
| `DELETE` | `/api/analyses/{id}` | Delete an analysis |
| `GET` | `/api/health` | Return `{ "status": "ok" }` |

Completed analysis responses include:

- cluster labels
- ticket counts and percentages
- extracted keywords
- representative tickets per cluster

---

## Testing

### Backend tests

```bash
cd backend
source .venv/bin/activate
pytest -m "not real_jira"
```

If `TEST_DATABASE_URL` is set, the backend test suite uses that database instead of starting PostgreSQL via `testcontainers`. This is the path used by GitHub Actions and by `docker-compose.test.yml`.

Inside the devcontainer, a host-managed Podman PostgreSQL service is typically reachable as `host.containers.internal`. For example:

```bash
export TEST_DATABASE_URL=postgresql+psycopg2://test:test@host.containers.internal:5433/clusterizer_test
pytest -m "not real_jira"
```

From the host, you can also run the compose-based test stack directly:

```bash
podman compose -f docker-compose.test.yml up --build backend-test
```

### Frontend build

```bash
cd frontend
npm ci
npm run build
```

## CI

GitHub Actions runs the workflow in `.github/workflows/ci.yml`.

- Backend: `pytest -m "not real_jira"` against a `pgvector/pgvector:pg18` PostgreSQL service container via `TEST_DATABASE_URL`
- Frontend: `npm ci` and `npm run build`

```bash
cd frontend
npm run build
```

---

## Real Jira integration tests

`docker-compose.test.yml` brings up a full end-to-end test stack:

- `db`: PostgreSQL 18 + pgvector for the app
- `jira-db`: PostgreSQL 17.9 for Jira
- `jira`: Atlassian Jira Software 11.3.4
- `jira-setup`: Playwright-based setup and issue seeding
- `backend-test`: pytest runner with real Jira environment variables enabled

### Run the full real Jira stack

```bash
export JIRA_LICENSE='...your Jira evaluation or developer license...'
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

`JIRA_LICENSE` is only required when you want the Playwright setup container to finish provisioning Jira and seed issues end-to-end.

It is not required for:

- regular backend tests with `cd backend && pytest`
- frontend builds with `cd frontend && npm run build`
- Jira setup smoke tests that stop at the license screen

There is no automatic license generation in this repo. Use a temporary Jira Software Data Center evaluation or developer license from Atlassian and provide it as either an exported shell variable, a value in a local root `.env` file, or a CI secret named `JIRA_LICENSE`.

### Smoke-test the Jira setup automation without a license

```bash
export JIRA_SETUP_STOP_AFTER=license
docker compose -f docker-compose.test.yml up jira-db jira jira-setup --build
```

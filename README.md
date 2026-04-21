# 🔮 The Clusterizer

Given a Jira instance URL, a PAT and a JQL query filter, this project creates clusters of ticket types using AI so you can discover which categories of issues are impacting you most.

| Layer | Technology |
|---|---|
| Frontend | Vanilla TypeScript (Vite, no framework) |
| Backend | Python · FastAPI |
| Embeddings | Ollama `/api/embed` (configurable model, default `nomic-embed-text`) |
| Cluster labels | Ollama `/api/generate` (configurable model, default `gemma3:4b`) |
| Clustering | scikit-learn · K-Means |
| Database | PostgreSQL 18 + [pgvector](https://github.com/pgvector/pgvector) |

---

## How it works

1. You provide a Jira URL, your API token (PAT), and a JQL filter.
2. The backend fetches all matching tickets via the Jira REST API.
3. Each ticket's summary + description is converted to a vector embedding via Ollama.
4. K-Means clustering groups tickets into *N* clusters.
5. An Ollama LLM generates human-readable cluster labels, with keyword fallback if the LLM is unavailable.
6. Results are stored in PostgreSQL (embeddings in pgvector, cluster metadata in regular tables).
7. The frontend polls for completion and displays interactive cluster cards.

---

## Quick start (Docker Compose)

```bash
# 1. Clone & enter the repo
git clone https://github.com/macel94/the-clusterizer.git
cd the-clusterizer

# 2. Start everything
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

---

## Dev Containers / GitHub Codespaces

This repo now includes a `.devcontainer/devcontainer.json` so you can open it directly in a local Dev Container or in GitHub Codespaces.

- the container installs Python 3.12, Node.js 24 and Docker tooling
- the initial setup creates `backend/.venv`, installs backend test dependencies, and runs `npm install` in `frontend/`
- ports `3000`, `8000`, `5432`, `5433`, `11434`, and `18080` are forwarded for the app and the real-Jira test stack

Once the Codespace/container is ready, use the same commands as in the local sections below.

> [!NOTE]
> The app still needs an Ollama endpoint. In Codespaces, the easiest option is usually to point `OLLAMA_URL` at a reachable external Ollama instance rather than trying to run a large local model inside the Codespace.

---

## Local development (without Docker)

### Prerequisites
* Python 3.11+
* Node.js 20+
* PostgreSQL 18 with the `pgvector` extension
* Ollama running locally

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/clusterizer \
OLLAMA_URL=http://localhost:11434 \
  uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

---

## Authentication

| Jira flavour | Username field | Token field |
|---|---|---|
| Cloud | Email address | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Server / Data Center | Leave blank | Personal Access Token (Bearer) |

---

## JQL examples

```
project = "OPS" AND status != Done
project in ("PLATFORM","INFRA") AND created >= -30d
issuetype = Bug AND priority in (High, Critical) AND status != Closed
```

---

## API reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyses` | Create and start a new analysis |
| `GET` | `/api/analyses` | List all analyses |
| `GET` | `/api/analyses/{id}` | Get analysis + cluster results |
| `DELETE` | `/api/analyses/{id}` | Delete an analysis |
| `GET` | `/api/health` | Health check |

---

## Real Jira integration tests

The repo includes a **real Jira** docker test stack for end-to-end validation. It starts:

- PostgreSQL 18 + pgvector for the app
- PostgreSQL 17 for Jira (supported by Jira 11.3)
- Jira Software 11.3.4
- a Playwright-based Jira setup/provisioning container that completes the setup wizard and seeds issues

### Run the full real-Jira test stack

```bash
# required only for the full Jira provisioning flow
export JIRA_LICENSE='...your Jira evaluation/developer license...'
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

`JIRA_LICENSE` is **not** required for:

- normal backend tests (`cd backend && pytest`)
- frontend builds (`cd frontend && npm run build`)
- the Jira setup smoke test that stops at the license screen

It is only required when you want the Playwright setup container to finish provisioning Jira and seed issues end-to-end, because Jira itself refuses to continue without a valid license key.

There is no automatic license generation in this repo. Use a temporary Jira Software Data Center evaluation/developer license obtained from Atlassian, then provide it as either:

- an exported shell variable (`export JIRA_LICENSE='...'`)
- a value in your local root `.env` file
- a CI secret exposed as `JIRA_LICENSE`

### Validate the Jira setup automation without a license

This stops right before the license entry step and is useful for smoke-testing the wizard automation locally:

```bash
export JIRA_SETUP_STOP_AFTER=license
docker compose -f docker-compose.test.yml up jira-db jira jira-setup --build
```

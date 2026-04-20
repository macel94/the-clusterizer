# 🔮 The Clusterizer

Given a Jira instance URL, a PAT and a JQL query filter, this project creates clusters of ticket types using AI so you can discover which categories of issues are impacting you most.

| Layer | Technology |
|---|---|
| Frontend | Vanilla TypeScript (Vite, no framework) |
| Backend | Python · FastAPI |
| Embeddings | [fastembed](https://github.com/qdrant/fastembed) – ONNX-based, no PyTorch |
| Clustering | scikit-learn · K-Means |
| Database | PostgreSQL 16 + [pgvector](https://github.com/pgvector/pgvector) |

---

## How it works

1. You provide a Jira URL, your API token (PAT), and a JQL filter.
2. The backend fetches all matching tickets via the Jira REST API.
3. Each ticket's summary + description is converted to a 384-dimensional vector embedding.
4. K-Means clustering groups tickets into *N* clusters.
5. Top keywords are extracted per cluster and used as human-readable labels.
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

## Local development (without Docker)

### Prerequisites
* Python 3.11+
* Node.js 20+
* PostgreSQL 16 with the `pgvector` extension

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgresql://user:pass@localhost:5432/clusterizer \
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

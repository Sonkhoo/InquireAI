# InquireAI

InquireAI is an enterprise RAG knowledge assistant for asking grounded questions over internal documents. It combines structure-aware document ingestion, hybrid retrieval, permission-aware context, and citation-backed answers in one workflow.

> Project status: active development. Some platform capabilities (auth, workspace management, full deployment) are still being built.


## Demo Flow
**Demo video:** [Watch the InquireAI demo](docs/media/demo-video.mp4)

## Architecture


### Ingestion pipeline

![InquireAI data ingestion architecture](docs/ingestion.png)

The ingestion path validates an upload, parses it with Docling, cleans and enriches the extracted content, creates structure-aware chunks, generates embeddings, and stores the chunks with access metadata for retrieval.

### Query pipeline

![InquireAI query architecture](docs/query.png)

The query path validates the request, applies workspace and role filters, retrieves relevant chunks via hybrid search, reranks and synthesizes the context, validates citations, and calculates confidence before returning an answer or abstention.

## Features

- Upload PDF, DOCX, XLSX, Markdown.
- Structure-aware parsing and chunking via Docling
- Hybrid retrieval: sparse BM25 + dense vector search with reciprocal-rank fusion
- Cross Encoder re-ranking
- Contextual chunk enrichment (Groq-generated summaries at ingestion time)
- Contextual query rewriting using session history
- Multi-hop retrieval with sufficiency checks
- Grounded answers with structured citations and citation validation
- Graceful abstention when evidence confidence falls below threshold
- RBAC filtering enforced at retrieval time, not after generation
- Guardrails: Prompt Guard injection detection, Presidio PII screening, Llama Guard content safety
- FastAPI backend with Logfire observability and LangSmith agent tracing
- React frontend with user impersonation, conversation management, and document ingestion panel

## Technology overview

| Area | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Agent orchestration | LangGraph |
| Document parsing | Docling |
| Embeddings | Jina Embeddings v4 via `sentence-transformers` |
| Vector store | Qdrant (dense + sparse BM25) |
| LLM | Openai/gpt-oss-120b, Openai/gpt-oss-20b |
| Reranking | Cross-encoder (`bge-reranker-base`) |
| Guardrails | Prompt Guard, Presidio, Llama Guard |
| Observability | Logfire |
| Database | PostgreSQL (sessions, messages, users, roles) |
| Frontend | React + TypeScript + Vite |

## Repository layout

```
InquireAI/
  server/
    app/
      api/routes/     FastAPI routes: chat, conversations, upload, users, health
      graph/          LangGraph pipeline: nodes, router, state
      ingestion/      Parse, clean, chunk, enrich, embed
      retrieval/      Hybrid search, reranking, confidence scoring, synthesis
      guardrails/     Prompt Guard, Presidio, Llama Guard
      memory/         Short-term session memory (PostgreSQL-backed)
      db/             Postgres connection pool and chunk storage
    main.py           FastAPI entry point
    tests/            Ingestion and parsing tests
  frontend/
    src/              React app: chat UI, upload panel, conversation management
```

## Demo setup

User authentication is skipped for the demo. Three users are seeded in the database and the frontend has a user dropdown that impersonates one of them. The API trusts the submitted email, resolves the user in Postgres, and enforces role checks server-side.

### Seeded users

| User | Email | Role | Purpose |
|---|---|---|---|
| John | `john@inquire.ai` | `admin` | Can ingest files |
| Alice | `alice@inquire.ai` | `engineer` | Allowed role — can chat over ingested docs |
| Bob | `bob@inquire.ai` | `marketer` | Disallowed role — cannot access ingested docs |

### End-to-end flow

1. **Ingest** — select John (admin), choose a file, set allowed roles, click Ingest Document. The file runs through parse → clean → chunk → enrich → embed → Qdrant.
2. **Switch user** — change to Alice (engineer) or Bob (marketer).
3. **Chat** — send a message. The backend resolves the user, runs the LangGraph pipeline with retrieval filtered to that user's accessible files, and returns a grounded answer with citations.
4. **Access control** — retrieval only surfaces chunks whose `allowed_role_ids` include the requesting user's role. Bob gets no evidence from files he can't access.

## Local development

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```powershell
cd server
uv sync
uv run uvicorn main:app --reload
```

API available at `http://localhost:8000`.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/files` | Upload and ingest a document |
| `POST` | `/api/chat/` | Send a chat message |
| `GET` | `/api/conversations/` | List conversations for a user |

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:5173`.

## Database schema

```sql
roles          (role_name PK, created_at)
workspaces     (id PK, name, description, created_at)
users          (id PK, email, display_name, password, role → roles, workspace_id → workspaces, created_at)
conversations  (id PK, user_id → users, workspace_id → workspaces, title, created_at, updated_at)
messages       (id PK, conversation_id → conversations, role, content, metadata jsonb, created_at)
```

Seeded roles: `admin`, `engineer`, `marketer`, `hr`, `user`.

Chunks and embeddings are stored in Qdrant, not Postgres. Each chunk payload carries `workspace_id`, `allowed_role_ids[]`, `file_id`, `chunk_index`, `text`, and `context_summary`.

## Tests

```powershell
cd server
uv run pytest
```

## Roadmap

- Complete authentication and workspace management
- Connect durable PostgreSQL, Qdrant, Redis, and S3-compatible storage adapters for production
- Add GitHub read-only retrieval via MCP
- Add full-profile visual PDF retrieval with ColPali and self-correction loop
- Add evaluation harness with Ragas and DeepEval
- Production deployment on Render

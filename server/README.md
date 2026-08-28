# InquireAI

InquireAI is an enterprise RAG knowledge assistant for asking grounded questions over internal documents. It combines structure-aware document ingestion, hybrid retrieval, permission-aware context, and citation-backed answers in one workflow.

> Project status: active development. The architecture and intended production workflow are documented here; some platform capabilities are still being built.

## Demo

**Demo video:** [Watch the InquireAI demo](docs/media/demo-video.mp4)

## Features

- Upload PDF, DOCX, XLSX, Markdown, and supported code files.
- Parse documents with structure-aware extraction and chunking.
- Combine sparse BM25 retrieval with dense vector search and reciprocal-rank fusion.
- Preserve document structure and attach workspace, role, and file metadata to chunks.
- Generate grounded answers with structured citations and citation validation.
- Return a graceful abstention when the evidence is not strong enough.
- Enforce access filtering during retrieval rather than after answer generation.
- Provide a FastAPI API and a Streamlit interface for local experimentation.
- Instrument the service with Logfire for application and system-metric observability.

## Architecture

### Data ingestion architecture


![InquireAI data ingestion architecture](docs/ingestion.png)

The ingestion path validates an upload, parses it with Docling, cleans and enriches the extracted content, creates structure-aware chunks, generates embeddings, and stores the chunks with access metadata for retrieval.

### Query architecture

![InquireAI query architecture](docs/query.png)

The query path validates the request, applies workspace and role filters, retrieves relevant chunks, reranks and synthesizes the context, validates citations, and calculates confidence before returning an answer or abstention.

### Technology overview

| Area | Technology |
| --- | --- |
| API | FastAPI + Uvicorn |
| Orchestration | LangGraph |
| Document parsing | Docling |
| Embeddings | Hugging Face sentence-transformers |
| Vector retrieval | Qdrant |
| Sparse retrieval | Qdrant / BM25 direction |
| Generation | Groq through LangChain |
| Guardrails | Prompt Guard, Presidio, and Sementic Similarity |
| Observability | Logfire |

## Repository layout

```text
InquireAI/
	app/
		api/          FastAPI routes for health, uploads, and chat
		graph/        LangGraph state, routing, and processing nodes
		ingestion/    Parsing, cleaning, chunking, enrichment, and embedding
		retrieval/    Hybrid retrieval, reranking, confidence, and synthesis
		guardrails/   Prompt and PII safety checks
	tests/          Ingestion and parsing tests
	main.py         FastAPI application entry point
	streamlit_app.py  Local interactive UI
```

## Demo flow (auth skipped)

User authentication is skipped for the demo. Instead, three users are seeded in the database and the frontend has a "Signed in as" dropdown that impersonates one of them. The API trusts the submitted email, looks the user up in Postgres, and enforces role checks server-side.

### Seeded demo users

| User | Email | Role | Purpose |
| --- | --- | --- | --- |
| John | `john@inquire.ai` | `admin` | Can ingest files |
| Alice | `alice@inquire.ai` | `engineer` | Allowed role — can chat over ingested docs |
| Bob | `bob@inquire.ai` | `marketer` | Disallowed role — cannot access ingested docs |

### End-to-end flow

1. **Ingest as admin** — select *John (admin)* in the frontend dropdown, choose a workspace and allowed roles, then upload a file via `POST /files`. The upload route looks up the user in the DB and rejects the request with `403` unless their role is `admin`. The file runs through the ingestion pipeline and chunks are stored with workspace + allowed-role metadata.
2. **Switch roles** — change the "Signed in as" dropdown to another seeded user (e.g. *Alice (engineer)*).
3. **Chat** — send a message via `POST /api/chat/`. On every request the backend:
   - resolves the user by email in the DB (`404` if unknown);
   - creates the conversation if it doesn't exist, or loads it if it does;
   - persists the user's message;
   - runs the LangGraph pipeline with retrieval filtered by the file's allowed roles;
   - persists the assistant turn with citations/confidence metadata.
4. **Access control** — retrieval only surfaces chunks whose allowed roles include a role granted to the current request, so Bob (disallowed) gets no evidence from files he can't access.

## Local development

The AI service requires Python 3.13 or newer and uses `uv` for dependency management.

```powershell
cd services/ai-service
uv sync
uv run uvicorn main:app --reload
```

The API is then available at `http://localhost:8000`.

Useful endpoints:

- `GET /health` - service health check
- `GET /version` - service version
- `POST /files` - upload and ingest a document
- `POST /api/chat/` - query the knowledge assistant

To run the Streamlit interface:

```powershell
cd services/ai-service
uv run streamlit run streamlit_app.py
```

## Tests

```powershell
cd services/ai-service
uv run pytest
```

## Documentation

- [Architecture document](Architecture%20Doc.md) - detailed system decisions, pipelines, guardrails, and deployment profiles.
- [AI service README](services/ai-service/README.md) - service-specific setup and development notes.

## Roadmap

- Complete authentication, workspace management, and role-based access flows.
- Connect durable PostgreSQL, Qdrant, Redis, and S3-compatible storage adapters.
- Add GitHub read-only retrieval through MCP.
- Add full-profile visual PDF retrieval with ColPali and cross-encoder reranking.
- Add evaluation workflows and the production deployment configuration.

# InquireAI - AI Enterprise Knowledge Assistant Architecture

The single source of truth for this project. Everything below reflects every decision made across planning — supersedes all earlier partial docs. Anything still genuinely open is marked ⚠️ with a recommendation, not just a question mark.

---

## 0. Tech Stack Summary

| Layer | Choice |
|---|---|
| Backend services (Auth, Ingestion) | TypeScript |
| AI Core (chat, retrieval, agents, vector storage) | Python |
| Services | 3 total: Auth & Admin (TS), Ingestion (TS), AI Core (Python — API + BullMQ worker, one codebase, two deployment profiles) |
| Ingestion parsing | **Docling** (PDF/DOCX/XLSX, structure-aware) + **ColPali** (visually-rich PDF pages — full profile only) |
| Embeddings | Qwen3-Embedding-0.6B via Hugging Face `sentence-transformers`, in-process inside AI Core |
| Chat/agent LLM | Groq (fast inference, open-weight models) |
| Reranker | Cross-encoder (e.g. `bge-reranker-base`), in-process — **full profile only** |
| Grounding | Lite: single confidence-threshold check. Full: LLM-as-judge + self-correction loop, retries ≤ 2. |
| Citation enforcement | Structured/function-calling output (grounded prompt forces citations as `chunk_id` references, never free text) + programmatic citation validation, both profiles |
| Query rewriting | Contextual (light, both profiles — resolves conversational references using session history) + self-correction rewrite (full profile only, triggered on ungrounded judge result) |
| Evaluation | **Ragas** + **DeepEval** — offline evaluation harness, separate from the runtime LLM-as-Judge (see §11) |
| GitHub connector auth | OAuth |
| Databases | PostgreSQL (system of record), Qdrant (document vectors + long-term memory, separate collections), Redis (BullMQ + caching + rate limiting) |
| File storage | S3-compatible API, LocalStack for local dev, disk-storage fallback behind the same interface |
| Long-term memory | Mem0 (V2), self-hosted, backed by Qdrant + Postgres |
| Deployment | **Render**, Docker containers. Auth & Admin + Ingestion + AI Core (**lite profile**) deployed. AI Core (**full profile**) runs **locally** for the demo — see §9. |
| Observability | Logfire (structured logging/tracing), LangSmith (LangGraph tracing), Prometheus (`/metrics`) |
| Guardrails | prompt guard and llama guard (sanitization), Presidio (PII detection/masking), tenacity (retries), slowapi (rate limiting) |


---

## 1. Core Logic

### Ingestion loop
1. **File validation** (TS Gateway) — MIME type check, extension whitelist (PDF/DOCX/XLSX/MD/code), size check (max ~10MB), page limit, duplicate hash check
2. Store file via `StorageAdapter` → write `files` row (`status: pending`)
3. Enqueue BullMQ job for processing
4. **Parse by type** (worker) — Docling for PDF/DOCX/XLSX (structure-aware: headings, tables), Tree-sitter for code
5. **Text cleaning** — Unicode normalization (NFC), remove control/zero-width characters, HTML/XML/Markdown sanitization, collapse whitespace
6. **Prompt Guard screening** — scan for injection patterns, log suspicious content (alert admin if threshold exceeded, do not block)
7. **Document cleaning** — remove headers/footers, deduplicate chunks, remove Base64 blobs
8. **Structure-aware chunking** — boundaries respect real structure (section/header for PDF/DOCX, table for XLSX, function/class for code); target ~512 tokens, 15% overlap as starting point, never split mid-section/mid-function
9. **Contextual summarization** — one Groq call per chunk generates 1-2 sentence context situating chunk within document (Anthropic-style contextual retrieval); prepend to chunk text before embedding. Async, no RAM cost.
10. **Metadata enrichment** — attach file_id, workspace_id, allowed_role_ids[], chunk_index, timestamps
11. Enqueue `embed-chunk` BullMQ job per chunk → `{ chunk_text, context_summary, workspace_id, allowed_role_ids[], file_id, chunk_index, metadata}`
12. AI Core worker consumes job → embed contextualized chunk via in-process Qwen3-Embedding → write vector + payload to Qdrant `documents` collection
13. **Full profile only:** additionally runs PDF through ColPali for visual page embeddings → separate `documents_visual` collection
14. No PII masking at ingestion — documents stored as-is; sensitive data handling deferred to query/response time based on role-specific policies
15. Worker writes ingestion status directly to Postgres
16. **On failure:** retry 3x exponential backoff (tenacity) → mark `failed`, surface in admin UI, never fail silently

### Query loop — shared steps (both profiles)
1. **Rate limiting** (slowapi) — per-user request throttle, configurable (start ~30 req/min)
2. **Request validation** — max length check, UTF-8 validation, content type check, empty query rejection
3. **Input sanitization** — Unicode normalization (NFC), remove control characters, HTML/Markdown sanitization (bleach)
4. **Authentication + RBAC** — verify JWT, resolve workspace, resolve `accessible_file_ids` (most-permissive-wins), resolve user permissions, cache RBAC result (~60s TTL, invalidated on permission change)
5. **Contextual query rewrite (light)** — one cheap Groq call resolves pronouns/references using `session_history` (e.g. "what about last quarter?" → "What was Q3 2025 revenue?"). Runs before routing, both profiles.
6. **Presidio screening** — detect sensitive patterns in query, log detected PII patterns (not values), do not mask user query (only mask retrieved content)
7. **Prompt Guard** — detect/flag prompt-injection, jailbreaks heuristics, log suspicious patterns, off topics
8. **Llama Guard (optional)** — content safety category classification, flag unsafe categories
9. **RBAC-safe cache check** — key = hash(`accessible_file_ids`) + hash(rewritten_query); never key on query text alone. Return cached result if hit.
10. **Router agent** — decides: `doc_search` / `github_tool` / `general_chat`
11. **Metadata filtering** — applied at Qdrant query itself, not post-hoc: always includes RBAC filter (`workspace_id` + `allowed_role_ids`), plus query-scoped filters surfaced by rewrite step (e.g., specific `file_id`, date range)

### Query loop — `doc_search`, **lite profile** (deployed to Render)
12. BM25 (Postgres FTS, sparse) + Dense search (Qdrant, Qwen3, RBAC + metadata filtered) → RRF fusion
13. **Context compression** — trim retrieved chunks to sentences actually relevant to query (token-budget and hallucination-risk reduction; cheap sentence-relevance filter, not a second LLM call)
14. **PII masking (query-time)** — apply Presidio masking to retrieved chunks before synthesis based on workspace/role policies
15. **Grounded prompt** — system prompt explicitly instructs model to answer only from provided chunks and cite every claim; **force citations** via structured/function-calling output, so citations are `chunk_id` references, not free-text
16. Synthesizer (Groq) drafts `{ answer, citations: [chunk_id, ...] }`
17. **Citation validation (programmatic)** — verify every cited `chunk_id` exists in retrieved set; strip/flag any that don't (cheap lookup, no LLM call)
18. **Confidence score (composite)** — combines retrieval/rerank score + citation coverage; below threshold → graceful non-answer, **no mention the file exists**
19. **Response caching & persistence** — cache result (RBAC-safe key), persist to `messages`, log to `audit_log` (all content already masked)

### Query loop — `doc_search`, **full profile** (local only)
12. BM25 + Dense + **ColPali** → RRF fusion (3-way) → **Cross-Encoder Reranker**
13. Context compression (same as lite, over reranked set)
14. **PII masking (query-time)** — apply Presidio masking to retrieved chunks (same as lite)
15. Grounded prompt + force citations (same mechanism as lite)
16. Draft Generation (Groq) → programmatic citation validation (same as lite)
17. **LLM-as-Judge** grounding check (temp=0) — deeper model-based check: is draft actually *supported* by evidence, not just citing real chunk IDs
18. Grounded → composite confidence score → Answer + Citations
19. Ungrounded → **Self-Correction**: if `retry_count < 2`, Increase-K (loop back to retrieval) or Rewrite-Query (loop back to Router with heavier self-correction rewrite); exhausted → **Graceful Abstention**
20. **Response caching & persistence** — cache result, persist to `messages`, log to `audit_log` (masked)

### Query loop — other branches (both profiles)
- `github_tool` (step 12): MCP call to GitHub (read-only, OAuth-scoped, response cached short-TTL) → Draft Generation (no PII masking for tool results — already trusted) → Answer. No self-correction loop applied — MCP results are already trustworthy by construction.
- `general_chat` (step 12): Draft Generation directly, no retrieval, no PII masking → Answer

### Query loop — closing steps (both profiles)
- All external/flaky calls (Groq, Qdrant, GitHub MCP) wrapped in tenacity retry policies — never retried on auth/4xx errors
- **Guardrails applied:** Presidio (PII masking before synthesis), Prompt Guard (injection detection), Llama Guard (content safety), rate limiting (slowapi)
- Response cached (RBAC-safe key), persisted to `messages`, logged to `audit_log`

### Key rules
- **All input validated & sanitized** — every query and every uploaded document passes through: request validation (UTF-8, length, type), Unicode normalization (NFC), control character removal, HTML/Markdown bleaching, content screening (Prompt Guard, Llama Guard)
- **Screening is non-blocking** — Presidio (PII patterns), Prompt Guard (injection heuristics), Llama Guard (safety categories) detect and log issues but do not hard-reject; alerts surface to admin if thresholds exceeded
- **Permission checks at retrieval time** — never post-hoc on generated answer; RBAC filter enforced at Qdrant query, never as a post-filter
- **Most-permissive-wins** — effective access = union across all a user's roles
- **Refusals never leak restricted content existence** — both profiles
- **Citations always structured** — `chunk_id` references via function-calling/JSON output, never free-text; cheap programmatic validation rather than fuzzy text matching; easy to catch & strip hallucinated citations pre-answer
- **PII masking at query-time** — documents stored unmasked for flexibility; Presidio masking applied per-role/workspace policy before synthesis, same masking applied to response content and audit logs
- **Retrieval terminology:** Sparse = BM25 (lexical). Dense = Qwen3 embeddings (semantic). Hybrid = RRF fusion (three-way in full profile with ColPali). Not adopted: Qdrant's native sparse+dense fusion (e.g. SPLADE).

---

## 2. User Flow

**Admin:** register → create/join workspace → add users → assign roles (⚠️ default set: `admin`/`contributor`/`viewer`, or your own naming) → connect GitHub via OAuth (redirect → consent → callback stores token, read-only scope) → upload files → assign file-level role access

**User:** log in → chat interface with workspace context → ask question → answer + inline clickable citations → ask GitHub-grounded question → same citation pattern via MCP tool result

**Non-happy paths:** unsupported file type → clear rejection; zero-workspace-access user → empty-state screen, not an error; GitHub token expired → surfaced clearly, not silent; restricted-file query → graceful non-answer; permission revoked mid-session → next message simply can't retrieve that file

---

## 3. Architecture Diagrams

Build in Excalidraw and/or Eraser (diagram-as-code generated separately).

### HLD
```
Client → Gateway (TS, JWT check)
              ├── Auth & Admin (TS)                              [Render]
              ├── Ingestion (TS) ── BullMQ job ──→ AI Core Worker (Python)  [Render]
              └── (chat requests) ── internal HTTP (API key) ──→ AI Core API (Python)
                                                         │
                    ┌─────────────────┬───────────────────┼───────────────┐
               PostgreSQL          Qdrant              Redis            Groq
          (system of record)  (docs + visual + memory) (BullMQ+cache)   (LLM API)

AI Core runs as two profiles from one codebase (AI_CORE_PROFILE=lite|full):
  lite (deployed, Render): BM25 + Qwen3-Embedding-0.6B dense retrieval, single confidence check
  full (local only):        + ColPali + cross-encoder reranker + self-correction loop
```
Trust boundary: only the Gateway is publicly reachable; AI Core additionally requires an internal API key header.

### RBAC-citation sequence (flagship demo — identical in both profiles)
```
User → Gateway: "What's in the restricted HR doc?"
Gateway → AI Core: rewritten query + accessible_file_ids (restricted doc excluded)
AI Core → Qdrant: vector search filtered by accessible_file_ids + metadata filters
Qdrant → AI Core: zero relevant chunks
AI Core → AI Core: composite confidence below threshold → refusal path
AI Core → Gateway → User: "I don't have information on that" (no existence leak)
```

### AI pipeline (LangGraph, full profile — lite profile skips the bracketed nodes)
```
START → Sanitize → Contextual Query Rewrite → Router (doc_search | github_tool | general_chat)
  doc_search  → Metadata Filter (RBAC + scoped filters)
              → BM25 + Dense [+ ColPali] → RRF [→ Reranker]
              → Context Compression → Grounded Prompt (force citations)
              → Draft Generation → Citation Validation (programmatic)
              → [LLM-as-Judge → grounded? no → Self-Correction (retry ≤2) → back to retrieval/Router]
              → Composite Confidence Score → Answer or Abstain
  github_tool → MCP Tool Call (GitHub, read-only) → Draft Generation → Answer
  general_chat→ Draft Generation (no retrieval) → Answer

State: { query, rewritten_query, user_context, session_history, long_term_memory(V2),
         retrieved_chunks[], tool_results, citations[], confidence, answer, retry_count }
```

### Query Pipeline (detailed validation & sanitization)
```
Query
  ↓
1. Rate Limiting
  ↓
2. Request Validation
   - max length check
   - UTF-8 validation
   - content type check
   - empty query rejection
  ↓
3. Input Sanitization
   - Unicode normalization (NFC)
   - Remove control characters
   - HTML/Markdown sanitization (bleach)
  ↓
4. Authentication + RBAC
   - Verify JWT token
   - Resolve workspace
   - Resolve accessible_file_ids (most-permissive-wins)
   - Resolve user permissions
  ↓
5. Query Rewriting
   - Contextual rewrite (light) — resolve pronouns/conversational refs via session_history
  ↓
6. Presidio PII Detection
   - Screen for sensitive patterns
   - Log detected PII patterns (not values)
  ↓
7. Prompt Guard (LLM security)
   - Detect/flag prompt-injection heuristics
   - Log suspicious patterns
  ↓
8. Llama Guard (content safety)
   - Category classification (optional safety check)
   - Flag unsafe categories
  ↓
9. RBAC-safe Cache Check
   - Key = hash(accessible_file_ids) + hash(rewritten_query)
  ↓
10. Embedding + Retrieval
   - Generate embedding for rewritten query
   - Dense search (Qdrant) + BM25 (Postgres) with RBAC + metadata filters
   - RRF fusion (+ reranker for full profile)
  ↓
11. Context Compression
   - Trim chunks to query-relevant sentences
  ↓
12. Synthesis & Citation Enforcement
   - Grounded prompt with structured output
   - Generate answer + citations
  ↓
13. PII Masking (Query-time)
   - Apply Presidio masking to retrieved chunks before synthesis
   - Mask based on workspace/role policies
  ↓
14. Citation Validation
   - Verify all cited chunk_ids exist in retrieved set
   - Strip/flag invalid citations
  ↓
15. Confidence Scoring
   - Composite: retrieval score + citation coverage
   - Below threshold → graceful non-answer
  ↓
Response cached (RBAC key) + persisted to messages + audit_log (masked)
```

### Upload Pipeline (detailed validation & sanitization)
```
Upload
  ↓
1. File Validation
   - MIME type check
   - Extension whitelist (PDF, DOCX, XLSX, MD, code)
   - Size check (max limit, e.g. 10MB)
   - Page limit if applicable (e.g. 500 pages for PDF)
   - Duplicate upload hash check (prevent re-ingestion of same file)
  ↓
2. Queue Job
   - Store file via StorageAdapter
   - Write files table row (status: pending)
   - Enqueue BullMQ job
  ↓
3. Parsing
   - Docling (PDF/DOCX/XLSX structure-aware)
   - Tree-sitter (code files)
  ↓
4. Text Cleaning
   - Unicode normalization (NFC)
   - Remove HTML/XML/Markdown artifacts
   - Sanitize with bleach if applicable
   - Remove zero-width/control characters
  ↓
5. Prompt Guard
   - Scan parsed text for injection patterns
   - Log suspicious content (do not block — alert admin if threshold exceeded)
  ↓
6. Document Cleaning
   - Remove headers/footers (document-level)
   - Deduplicate identical chunks
   - Remove Base64 blobs
   - Collapse excessive whitespace
  ↓
7. Structure-aware Chunking
   - Respect document structure (sections, tables, functions)
   - Target ~512 tokens, 15% overlap
   - Never split mid-section/mid-function
  ↓
8. Metadata Enrichment
   - Per-chunk contextual summarization (Groq)
   - File metadata (file_id, workspace_id, allowed_role_ids)
   - Chunk index, timestamps
  ↓
9. Embedding
   - Qwen3-Embedding-0.6B (in-process)
   - Dense vectors for semantic search
   - [ColPali visual embeddings — full profile only]
  ↓
10. Storage to Vector DB
   - Write embeddings + metadata to Qdrant documents collection
   - [Write visual embeddings to documents_visual — full profile only]
   - Update ingestion_status to success
  ↓
On failure: retry 3x exponential backoff → mark failed, surface in admin UI
```

---

## 4. API Endpoints (representative)

All under `/v1/`, consistent error shape `{ error: { code, message } }`.

**Auth & Admin (TS):** `POST /auth/register`, `POST /auth/login` (public) · `POST /admin/workspaces`, `POST /admin/roles`, `POST /admin/users/:id/roles` (admin-only) · `GET /auth/github/oauth`, `GET /auth/github/callback` (OAuth flow)

**Ingestion (TS):** `POST /files` (upload, authenticated) · `GET /files/:id/status` · `POST /files/:id/permissions` (admin-only)

**AI Core (Python) — internal only, not publicly reachable:**
`POST /internal/chat` (called only via Gateway, requires internal API key, rate-limited via slowapi) · `GET /health`, `GET /ready` · `GET /metrics` (Prometheus) · Worker has no HTTP endpoints, pure BullMQ consumer

---

## 5. Database Design

### PostgreSQL
```
users             (id, email, password_hash, created_at)
roles             (id, name, workspace_id)
user_roles        (user_id, role_id)
workspaces        (id, name, owner_id, created_at)
files             (id, workspace_id, filename, storage_backend, storage_key, status, created_at, deleted_at)
file_permissions  (file_id, role_id, deleted_at)
ingestion_status  (file_id, state, error_message, updated_at)
chat_sessions     (id, user_id, workspace_id, created_at)
messages          (id, session_id, role, content, citations_json, confidence, created_at)
audit_log         (id, user_id, action, resource_id, allowed, created_at)
github_connections(id, workspace_id, access_token_encrypted, scope, created_at)
```
Soft delete (`deleted_at`) on `files` and `file_permissions` for audit integrity. `created_at`/`updated_at` everywhere.

### File storage — S3-compatible with fallback
One `StorageAdapter` interface (`upload`, `getSignedUrl`, `delete`) with S3 (LocalStack dev, real S3-compatible prod) and disk-adapter fallback implementations. Files table carries `storage_backend` + `storage_key`, not a hardcoded path.

### Qdrant — three collections
- `documents`: RBAC-scoped text embeddings. Payload = `workspace_id`, `allowed_role_ids[]`, `file_id`, `chunk_index`, `text` (contextualized), `context_summary`. Index `workspace_id` + `allowed_role_ids`.
- `documents_visual` (**full profile only**): ColPali multi-vector embeddings, same RBAC payload shape. Kept separate — different vector shape, full-profile-only feature.
- `memory` (V2, Mem0-backed): scoped per `user_id` only, no role logic.

### Redis
BullMQ queue `embed-chunk-queue` · RBAC permission cache (`acl:{user_id}`, ~60s TTL) · RBAC-safe response cache · rate-limiting counters (slowapi backend)

---

## 6. Requirements

**Functional:** enforce file-level RBAC at retrieval time · return graceful non-answers without revealing restricted content's existence · ground every answer in retrieved chunks with structured, validated citations · support async ingestion without blocking uploads · GitHub-grounded Q&A via read-only OAuth scope · sanitize and screen all user input · mask PII before anything is logged or cached (once, at ingestion, for document content; per-request for query content)

**Non-functional:** retrieval response time target < 3s end-to-end for the lite profile · full profile latency is not demo-time-critical since it runs locally · max upload file size ⚠️ pick one, e.g. 10MB · concurrent session target: 5–10 concurrent demo users · rate limit: start at 30 req/min per user (⚠️ tune)

**Constraints:** Qdrant Cloud free tier vector/collection limits (now three collections, not two — check this against your free-tier quota) · Render free tier cold starts · only the lite profile needs to fit Render's free-tier RAM

**Security requirement (explicit):** permission checks happen at retrieval time, never as a display-layer filter

---

## 7. Features (MoSCoW)

| Feature | Priority | Version | Deployed profile |
|---|---|---|---|
| Hybrid retrieval (BM25+vector+RRF) | Must | V1 | Lite + Full |
| Contextual summarization (ingestion-time) | Must | V1 | Lite + Full |
| Contextual query rewrite (light, session-aware) | Must | V1 | Lite + Full |
| Metadata filtering (RBAC + scoped filters) | Must | V1 | Lite + Full |
| Context compression | Must | V1 | Lite + Full |
| Grounded prompt + forced structured citations | Must | V1 | Lite + Full |
| Citation validation (programmatic) | Must | V1 | Lite + Full |
| Composite confidence score | Must | V1 | Lite + Full |
| RBAC-enforced citation grounding | Must | V1 | Lite + Full |
| LangGraph router/agents | Must | V1 | Lite + Full |
| GitHub MCP connector (OAuth, read-only) | Must | V1 | Lite + Full |
| Short-term session memory | Must | V1 | Lite + Full |
| Production tooling (Logfire, LangSmith, Presidio, bleach, tenacity, slowapi, Prometheus) | Must | V1 | Lite + Full |
| Redis caching (RBAC-safe + guardrails caching) | Must | V1 | Lite + Full |
| Evaluation harness (Ragas + DeepEval) | Must | V1 | Offline, both profiles |
| Cross-encoder reranker | Must | V1 | **Full only, local** |
| ColPali (visually-rich PDF retrieval) | Must | V1 | **Full only, local** |
| Self-correcting grounding loop (LLM-judge + retries) | Must | V1 | **Full only, local** |
| Generated-questions chunk enrichment | Could | V1.5 (optional) | — |
| Mem0-based long-term memory | Should | V2 | — |
| Additional connectors (Jira, Slack) | Could | V2 | — |
| Action agents (write operations) | Could | V2 | — |
| NGINX API gateway, Kubernetes | Won't (for now) | V2 | — |

---

## 8. Memory Architecture

**Short-term (V1):** conversation buffer, `messages` table is source of truth, last ~10 turns loaded into LangGraph state per request, summarize once history exceeds a token budget (⚠️ pick a starting number, e.g. ~2-3k tokens).

**Long-term (V2, Mem0):** self-hosted Mem0, backed by the `memory` Qdrant collection + Postgres. Scoped by `user_id`. Kept structurally and access-wise separate from document RAG.

---

## 9. Deployment — Render (Docker), with a local/deployed split for AI Core

**Decision:** Render, deployed via Docker containers per service. No AWS, no Fly.io.

AI Core runs as **two profiles from the same codebase**, switched by `AI_CORE_PROFILE=lite|full`:

| | **Lite profile** (Render) | **Full profile** (local only) |
|---|---|---|
| Embeddings | Qwen3-Embedding-0.6B, in-process | Same |
| Retrieval | BM25 + dense vector search | BM25 + dense + ColPali |
| Ranking | RRF only | RRF → cross-encoder reranker |
| Grounding | Single confidence-threshold check | Full LLM-as-judge + self-correction (retries ≤ 2) |
| Runs on | Render container | Your own machine (Docker Compose) |

Your deployed URL is a real, working, live demo running the simpler path. The full architecture is demoed locally. Be upfront about which is which.

⚠️ **Design intent:** one LangGraph with conditional skip-logic per node when `AI_CORE_PROFILE=lite`, not a forked codebase.

### What deploys to Render
Auth & Admin (TS), Ingestion (TS), AI Core lite profile (Python — API server + BullMQ worker)

### What runs locally only
AI Core full profile — ColPali indexing/retrieval, reranker, self-correction loop.

⚠️ **Demo data flow:** pre-ingest your demo documents locally (full profile) before showing the deployed app.

### Render deployment specifics
- Each service deploys from its own Dockerfile as a separate Render web service
- AI Core's dual entry point needs **two** Render services pointing at the same image (API command vs worker command)
- Managed Postgres/Redis via Render add-ons; Qdrant via Qdrant Cloud free tier

---

## 10. Production-Grade Tooling & Enhancements

| Concern | Tool | Notes |
|---|---|---|
| Structured logging | **Logfire** | Auto-instruments FastAPI; logs `retrieval_latency_ms`, `confidence_score`, `refusal_triggered` as structured fields |
| Agent tracing | **LangSmith** | Traces LangGraph node-by-node execution |
| Input sanitization | **bleach** | Strips HTML/script content before chunking/embedding/prompts |
| Prompt-injection screening | Heuristic keyword check | Flag and log, don't hard-block |
| PII detection/masking | **Presidio** | Applied once at ingestion for document content; per-query for chat input. Never log unmasked content. |
| Retries | **tenacity** | Different policies per call type; never retry on 4xx/auth errors |
| Rate limiting | **slowapi** | Redis-backed, per-user sliding window, start at 30 req/min |
| Response caching | Redis, custom keying | Cache key must include a hash of `accessible_file_ids`, never query text alone |
| **Guardrails caching** | Redis | PII-masking output cached at ingestion (mask once, not per-log-line); prompt-injection screening result piggybacks on the RBAC-safe response cache key for identical repeated queries |
| Metrics | **prometheus-fastapi-instrumentator** | Exposes `/metrics`, near-zero code |
| Health checks | Custom `/health` + `/ready` | Readiness checks Postgres/Redis/Qdrant connectivity |

**Testing additions:**
- RBAC resolution test suite — table-driven, enumerate role/permission combinations
- Contract tests between TS and Python — shared OpenAPI spec + schema validation
- Basic k6 load test — real p95 latency number to cite
- Minimal CI — GitHub Actions: lint + test on push

**Additional observability:**
- Trace ID propagation across the TS→Python HTTP call and the BullMQ job payload
- `audit_log` surfaced as a simple admin-viewable log

---

## 11. Evaluation Harness (Ragas + DeepEval)

Distinct from the runtime **LLM-as-Judge** (§1) — that's a per-request, live grounding check on one answer. This is an **offline harness**, run periodically or in CI against a fixed labeled dataset, producing aggregate metrics you can actually cite.

**What to build:**
- A small labeled eval set — 20-30 queries with known-correct source chunks/answers, covering: normal retrieval, restricted-doc refusal cases, GitHub-tool questions, general chat
- **Ragas metrics:** faithfulness (is the answer supported by retrieved context), answer relevancy, context precision, context recall — run against your retrieval + generation pipeline
- **DeepEval:** pytest-style test cases for hallucination detection and contextual relevancy, integrates cleanly with the minimal CI pipeline from §10

**Why this matters for your resume:** "faithfulness: 0.92 across 30 test queries, measured with Ragas" is a concrete, verifiable claim — a meaningfully stronger interview answer than an unverified "the RAG pipeline works well."

⚠️ Build the eval dataset *as you build* Layer 0 (§12) — write down a query and its expected source the first time you manually verify something works, rather than trying to reconstruct a labeled set retroactively at the end.

---

## 12. Layered Build Strategy

| Layer | Contents | Status | Cut rule |
|---|---|---|---|
| **Layer 0** | BM25 + Dense + RRF + grounded prompt + forced citations + citation validation + composite confidence + refusal (the entire lite profile) | **Must fully work — non-negotiable checkpoint.** | Never cut. |
| **Layer 0.5** | Contextual summarization (ingestion), contextual query rewrite, context compression, metadata filtering, guardrails caching | Cheap additions, build alongside Layer 0 | Never cut — none of these are expensive |
| **Layer 1** | Cross-encoder reranker | ~1 day once Layer 0 works | Cut if Layer 0 slips |
| **Layer 2** | ColPali | Timebox hard (e.g. 5 days) — highest single risk | Cut to "designed, not integrated" if it fights past the timebox |
| **Layer 3** | Self-correction loop (LLM-judge + retries) | Layer 0's single confidence-check already gives a working demo without it | Cut last |
| **Ongoing** | Evaluation harness (Ragas/DeepEval) | Build the eval dataset alongside Layer 0, run metrics as each layer lands | — |

Build and fully test Layer 0 + 0.5 in isolation before touching Layer 2 or 3 code.

---

## 13. Codebase Scaffold

`ai-core-scaffold.zip` — FastAPI shell with Logfire, LangSmith, slowapi, Prometheus, Presidio, bleach, tenacity, and RBAC-safe caching already wired. `run_retrieval_pipeline()` in `chat.py` is the intentional stub — that's where Layer 0 + 0.5 get built next.

---

## 14. Open Items — resolve before Week 1
1. AI Core's RAM footprint on Render, lite profile only — test early
2. Exact chunk size/overlap and confidence threshold — empirical
3. Default role set naming
4. Max upload file size
5. Storage adapter: S3 (LocalStack) first, or disk first if time-constrained
6. Lite/full profile branching design — one LangGraph with conditional skip-logic (recommended)
7. Demo data flow for ColPali — pre-ingest locally before showing the deployed app
8. Contextual-summarization prompt design — exact template, and whether to fold in generated-questions
9. Composite confidence score formula — exact weighting between retrieval relevance and citation coverage, needs empirical tuning
10. Eval dataset — build incrementally from Day 1, don't leave it until the end
11. Internal API key mechanism specifics (header name, rotation)

"""Streamlit demonstration client for the InquireAI RAG API.

Chat-first UI inspired by ChatGPT / Gemini:
    - Sidebar with chat history
    - Centered conversation column
    - Pinned chat input at the bottom
    - Welcome screen with clickable suggestions
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import streamlit as st


SUPPORTED_TYPES = ["pdf", "docx", "xlsx", "md"]
DEFAULT_API_URL = os.getenv("INQUIRE_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="INQUIRE AI",
    page_icon="I",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Styling — ChatGPT/Gemini-like look
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
        /* Hide default chrome (keep header for sidebar toggle) */
        #MainMenu, footer { visibility: hidden; }

        /* Header: transparent, no overlap, hide Deploy button + status */
        [data-testid="stHeader"] {
            background: transparent;
            height: 0rem;
        }
        [data-testid="stHeader"] [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {
            display: none;
        }

        /* Main scroll container — keep it scrollable, pad bottom so the
           pinned chat input never covers the last messages */
        [data-testid="stMain"],
        section.main {
            overflow: auto !important;
        }
        [data-testid="stMainBlockContainer"] {
            padding: 1.5rem 1rem 8rem 1rem;
            max-width: 100%;
        }

        /* Sidebar — pinned open, collapse button hidden */
        section[data-testid="stSidebar"] {
            background: rgba(128, 128, 160, 0.05);
            border-right: 1px solid rgba(128, 128, 160, 0.15);
        }
        section[data-testid="stSidebar"] button[kind="header"],
        section[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
            display: none;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none;
        }

        /* Centered chat column */
        .chat-col .block-container { max-width: 820px; margin: 0 auto; }

        /* Welcome screen */
        .welcome {
            text-align: center;
            padding: 14vh 1rem 2rem 1rem;
        }
        .welcome h1 {
            font-size: 2.4rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
        }
        .welcome p { color: #8b8b9e; font-size: 1.05rem; }

        /* Suggestion cards */
        .stButton > button.suggestion-btn {
            width: 100%;
            text-align: left;
            border-radius: 12px;
            border: 1px solid rgba(128, 128, 160, 0.25);
            background: rgba(128, 128, 160, 0.06);
            padding: 0.8rem 1rem;
            font-size: 0.9rem;
            color: inherit;
        }
        .stButton > button.suggestion-btn:hover {
            background: rgba(128, 128, 160, 0.14);
            border-color: rgba(128, 128, 160, 0.45);
        }

        /* Citation chips */
        .citation {
            background: rgba(128, 128, 160, 0.10);
            border: 1px solid rgba(128, 128, 160, 0.25);
            border-radius: 8px;
            padding: 0.4rem 0.7rem;
            margin: 0.3rem 0;
            font-size: 0.8rem;
        }
        .citation-id {
            color: #8b8b9e;
            font-family: monospace;
            font-size: 0.7rem;
        }

        /* Meta line under assistant answers */
        .meta-line {
            color: #8b8b9e;
            font-size: 0.75rem;
            margin-top: 0.25rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_url(path: str) -> str:
    return f"{st.session_state.api_url.rstrip('/')}/{path.lstrip('/')}"


def error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text

        return f"API error {exc.response.status_code}: {detail}"

    return f"Could not reach the API: {exc}"


def request_json(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    with httpx.Client(timeout=180.0) as client:
        response = client.request(method, api_url(path), **kwargs)
        response.raise_for_status()
        return response.json()


def create_chat(title: str = "New conversation") -> str:
    """Create a temporary frontend-only chat."""
    thread_id = str(uuid.uuid4())
    st.session_state.chats[thread_id] = {"title": title, "messages": []}
    return thread_id


def switch_chat(thread_id: str) -> None:
    st.session_state.thread_id = thread_id
    st.session_state.messages = st.session_state.chats[thread_id]["messages"]


def new_chat() -> None:
    switch_chat(create_chat())


def delete_chat(thread_id: str) -> None:
    st.session_state.chats.pop(thread_id, None)

    if not st.session_state.chats:
        create_chat()

    if st.session_state.thread_id not in st.session_state.chats:
        thread_id = next(iter(st.session_state.chats))

    switch_chat(thread_id)


def update_chat_title(thread_id: str, question: str) -> None:
    """Use the first question as a temporary chat title."""
    chat = st.session_state.chats[thread_id]

    if chat["title"] == "New conversation":
        title = question.strip().replace("\n", " ")
        if len(title) > 40:
            title = f"{title[:40]}..."
        chat["title"] = title or "New conversation"


def send_question(question: str) -> None:
    """Append the user message, call the API, and store the answer."""
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.chats[st.session_state.thread_id]["messages"] = (
        st.session_state.messages
    )
    update_chat_title(st.session_state.thread_id, question)

    with st.chat_message("assistant", avatar="🤖"):
        with st.status("Searching and synthesizing...", expanded=False) as status:
            try:
                result = request_json(
                    "POST",
                    "/api/chat/",
                    json={
                        "message": question,
                        "thread_id": st.session_state.thread_id,
                        "workspace_id": st.session_state.workspace_id,
                        "allowed_role_ids": st.session_state.role_ids,
                        "session_history": st.session_state.messages[:-1],
                    },
                )

                status.update(label="Answer ready", state="complete")

                response_text = result.get("response", "No answer returned.")
                st.markdown(response_text)
                render_assistant_meta(result)
                render_citations(result.get("citations", []))

                st.session_state.messages.append(
                    {"role": "assistant", "content": response_text, "meta": result}
                )
                st.session_state.chats[st.session_state.thread_id]["messages"] = (
                    st.session_state.messages
                )

            except (httpx.HTTPError, ValueError) as exc:
                status.update(label="Request failed", state="error")
                st.error(error_message(exc))

                # Remove user message if API request failed.
                st.session_state.messages.pop()
                st.session_state.chats[st.session_state.thread_id]["messages"] = (
                    st.session_state.messages
                )


def render_citations(citations: list[dict[str, Any]]) -> None:
    """Render source citations as a collapsible list."""
    if not citations:
        return

    with st.expander(f"📚 Sources ({len(citations)})", expanded=False):
        for citation in citations:
            label = citation.get("filename") or citation.get("file_id", "source")
            page = citation.get("page_start")
            page_label = f" · page {page}" if page else ""
            chunk_id = citation.get("chunk_id", "")

            st.markdown(
                f"""
                <div class='citation'>
                    <b>{label}</b>{page_label}
                    <br>
                    <span class='citation-id'>{chunk_id}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_assistant_meta(meta: dict[str, Any]) -> None:
    """Render model / time / confidence caption."""
    confidence = meta.get("confidence")
    confidence_label = f"{confidence:.2f}" if confidence is not None else "n/a"

    st.markdown(
        f"""
        <div class='meta-line'>
            {meta.get('model_used', 'unknown')} ·
            {meta.get('processing_time', 0):.2f}s ·
            confidence {confidence_label}
        </div>
        """,
        unsafe_allow_html=True,
    )


SUGGESTIONS = [
    "Summarize the key points of the uploaded document",
    "What are the main risks mentioned?",
    "List any deadlines or dates referenced",
]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "api_url" not in st.session_state:
    st.session_state.api_url = DEFAULT_API_URL

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "thread_id" not in st.session_state:
    st.session_state.thread_id = create_chat()

if "messages" not in st.session_state:
    st.session_state.messages = st.session_state.chats[
        st.session_state.thread_id
    ]["messages"]

if "uploads" not in st.session_state:
    st.session_state.uploads = []

if "workspace_id" not in st.session_state:
    st.session_state.workspace_id = "demo-workspace"

if "role_ids" not in st.session_state:
    st.session_state.role_ids = ["viewer", "admin"]


# ---------------------------------------------------------------------------
# Sidebar — chat history + settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("INQUIRE AI")

    if st.button(
        "＋ New chat",
        use_container_width=True,
        type="primary",
    ):
        new_chat()
        st.rerun()

    st.markdown("")

    # Chat history list
    for thread_id, chat in list(st.session_state.chats.items()):
        is_active = thread_id == st.session_state.thread_id
        label_col, delete_col = st.columns([5, 1])

        button_label = f"● {chat['title']}" if is_active else chat["title"]

        if label_col.button(
            button_label,
            key=f"chat_{thread_id}",
            use_container_width=True,
        ):
            switch_chat(thread_id)
            st.rerun()

        if delete_col.button("🗑", key=f"delete_{thread_id}", help="Delete chat"):
            delete_chat(thread_id)
            st.rerun()

    st.divider()

    # Settings (collapsed by default, like a real chat tool)
    with st.expander("⚙️ Settings & documents"):
        st.session_state.api_url = st.text_input(
            "AI service URL",
            value=st.session_state.api_url,
        )

        st.session_state.workspace_id = st.selectbox(
            "Workspace",
            options=["demo-workspace", "engineering", "finance", "hr"],
            index=0,
        )

        st.session_state.role_ids = st.multiselect(
            "Allowed roles",
            options=["viewer", "admin", "manager"],
            default=st.session_state.role_ids,
        )

        st.caption(
            "Workspace and role scope are sent with every upload and question."
        )

        st.divider()

        # ---------------------------------------------------------------
        # Document upload
        # ---------------------------------------------------------------

        uploaded_file = st.file_uploader(
            "Add a knowledge source",
            type=SUPPORTED_TYPES,
        )

        if uploaded_file and st.button(
            "Ingest document",
            type="primary",
            use_container_width=True,
        ):
            if (
                not st.session_state.workspace_id.strip()
                or not st.session_state.role_ids
            ):
                st.error(
                    "Select a workspace and at least one allowed role first."
                )
            else:
                with st.status(
                    "Running ingestion pipeline...",
                    expanded=True,
                ) as status:
                    try:
                        result = request_json(
                            "POST",
                            "/files",
                            files={
                                "file": (
                                    uploaded_file.name,
                                    uploaded_file.getvalue(),
                                    uploaded_file.type,
                                )
                            },
                            data={
                                "workspace_id": st.session_state.workspace_id.strip(),
                                "allowed_role_ids": ",".join(
                                    st.session_state.role_ids
                                ),
                            },
                        )

                        st.session_state.uploads.append(result)
                        status.update(
                            label="Document ready for retrieval",
                            state="complete",
                        )

                    except (httpx.HTTPError, ValueError) as exc:
                        status.update(label="Ingestion failed", state="error")
                        st.error(error_message(exc))

        if st.session_state.uploads:
            st.markdown("**Ingested this session**")

            for upload in st.session_state.uploads:
                st.success(
                    f"{upload['filename']} | {upload['chunks_stored']} chunks"
                )


# ===========================================================================
# Main chat area
# ===========================================================================

# -----------------------------------------------------------------------
# Welcome screen (empty chat)
# -----------------------------------------------------------------------

if not st.session_state.messages:
    st.markdown(
        """
        <div class='welcome'>
            <h1>INQUIRE AI</h1>
            <p>Ask anything about your documents — answers are grounded with citations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Clickable suggestion cards
    cols = st.columns(len(SUGGESTIONS))
    for col, suggestion in zip(cols, SUGGESTIONS):
        with col:
            if st.button(
                suggestion,
                key=f"suggest_{suggestion}",
                use_container_width=True,
            ):
                st.session_state.pending_question = suggestion
                st.rerun()

# -----------------------------------------------------------------------
# Conversation
# -----------------------------------------------------------------------

else:
    for message in st.session_state.messages:
        avatar = "🧑‍💻" if message["role"] == "user" else "🤖"

        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])

            if message["role"] == "assistant" and message.get("meta"):
                render_assistant_meta(message["meta"])
                render_citations(message["meta"].get("citations", []))

# -----------------------------------------------------------------------
# Pinned chat input (always rendered, like ChatGPT/Gemini)
# -----------------------------------------------------------------------

question = st.chat_input("Message INQUIRE AI...")

# Suggestion click from the welcome screen
if not question and st.session_state.get("pending_question"):
    question = st.session_state.pending_question
    st.session_state.pending_question = None

if question:
    if (
        not st.session_state.workspace_id.strip()
        or not st.session_state.role_ids
    ):
        st.error("Select a workspace and at least one allowed role first.")
    else:
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(question)

        send_question(question)
        st.rerun()
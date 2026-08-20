"""Streamlit demonstration client for the InquireAI RAG API."""

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
        response = client.request(
            method,
            api_url(path),
            **kwargs,
        )
        response.raise_for_status()
        return response.json()


def create_chat(title: str = "New conversation") -> str:
    """Create a temporary frontend-only chat."""
    thread_id = str(uuid.uuid4())

    st.session_state.chats[thread_id] = {
        "title": title,
        "messages": [],
    }

    return thread_id


def switch_chat(thread_id: str) -> None:
    """Switch the active temporary chat."""
    st.session_state.thread_id = thread_id
    st.session_state.messages = st.session_state.chats[thread_id]["messages"]


def new_chat() -> None:
    """Create and activate a new temporary chat."""
    thread_id = create_chat()
    switch_chat(thread_id)


def update_chat_title(thread_id: str, question: str) -> None:
    """Use the first question as a temporary chat title."""
    chat = st.session_state.chats[thread_id]

    if chat["title"] == "New conversation":
        title = question.strip().replace("\n", " ")

        if len(title) > 40:
            title = f"{title[:40]}..."

        chat["title"] = title or "New conversation"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "api_url" not in st.session_state:
    st.session_state.api_url = DEFAULT_API_URL

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "thread_id" not in st.session_state:
    thread_id = create_chat()
    st.session_state.thread_id = thread_id

if "messages" not in st.session_state:
    st.session_state.messages = st.session_state.chats[
        st.session_state.thread_id
    ]["messages"]

if "uploads" not in st.session_state:
    st.session_state.uploads = []


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("INQUIRE AI")

    st.caption(
        "Deterministic, RBAC enabled production RAG pipeline"
    )

    st.session_state.api_url = st.text_input(
        "AI service URL",
        value=st.session_state.api_url,
    )

    # -----------------------------------------------------------------------
    # Temporary frontend-only workspace options.
    #
    # Later replace these with data loaded from your backend.
    # -----------------------------------------------------------------------

    workspace_options = [
        "demo-workspace",
        "engineering",
        "finance",
        "hr",
    ]

    workspace_id = st.selectbox(
        "Workspace",
        options=workspace_options,
        index=0,
    )

    role_options = [
        "viewer",
        "admin",
        "manager",
    ]

    role_ids = st.multiselect(
        "Allowed roles",
        options=role_options,
        default=["viewer", "admin"],
    )

    st.caption(
        "Workspace and role scope are sent with every upload and question."
    )

    st.divider()

    # -----------------------------------------------------------------------
    # Chats
    # -----------------------------------------------------------------------

    st.subheader("Chats")

    if st.button(
        "+ New chat",
        use_container_width=True,
        type="primary",
    ):
        new_chat()
        st.rerun()

    st.markdown("")

    for thread_id, chat in st.session_state.chats.items():
        is_active = thread_id == st.session_state.thread_id

        button_label = chat["title"]

        if is_active:
            button_label = f"● {button_label}"

        if st.button(
            button_label,
            key=f"chat_{thread_id}",
            use_container_width=True,
        ):
            switch_chat(thread_id)
            st.rerun()

    st.divider()

    st.caption("Current thread")
    st.code(
        st.session_state.thread_id,
        language=None,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


st.title("INQUIRE AI.")

st.markdown(
    "<p class='subtitle'>"
    "Upload a knowledge source, apply its access scope, "
    "and ask a grounded question through the live RAG pipeline."
    "</p>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

left, right = st.columns(
    [1.1, 1.9],
    gap="large",
)


# ===========================================================================
# Upload section
# ===========================================================================

with left:
    st.subheader("1. Add a source")

    uploaded_file = st.file_uploader(
        "Choose a document",
        type=SUPPORTED_TYPES,
    )

    if uploaded_file and st.button(
        "Ingest document",
        type="primary",
        use_container_width=True,
    ):
        if not workspace_id.strip() or not role_ids:
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
                            "workspace_id": workspace_id.strip(),
                            "allowed_role_ids": ",".join(role_ids),
                        },
                    )

                    st.session_state.uploads.append(result)

                    status.update(
                        label="Document ready for retrieval",
                        state="complete",
                    )

                except (httpx.HTTPError, ValueError) as exc:
                    status.update(
                        label="Ingestion failed",
                        state="error",
                    )

                    st.error(error_message(exc))

    if st.session_state.uploads:
        st.markdown("**Ingested this session**")

        for upload in st.session_state.uploads:
            st.success(
                f"{upload['filename']} | "
                f"{upload['chunks_stored']} chunks"
            )


# ===========================================================================
# Chat section
# ===========================================================================

with right:
    st.subheader("2. Ask a question")

    # -----------------------------------------------------------------------
    # Render existing messages
    # -----------------------------------------------------------------------

    for message in st.session_state.messages:

        with st.chat_message(message["role"]):

            st.markdown(message["content"])

            if message.get("meta"):
                meta = message["meta"]

                confidence = meta.get("confidence")

                confidence_label = (
                    f"{confidence:.2f}"
                    if confidence is not None
                    else "n/a"
                )

                st.caption(
                    f"{meta.get('model_used', 'unknown')} | "
                    f"{meta.get('processing_time', 0):.2f}s | "
                    f"confidence {confidence_label}"
                )

                for citation in meta.get("citations", []):

                    label = (
                        citation.get("filename")
                        or citation.get("file_id", "source")
                    )

                    pages = citation.get("page_start")

                    page_label = (
                        f" | page {pages}"
                        if pages
                        else ""
                    )

                    st.markdown(
                        f"""
                        <div class='citation'>
                            <b>{label}</b>{page_label}
                            <br>
                            <span class='citation-id'>
                                {citation.get('chunk_id', '')}
                            </span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    # -----------------------------------------------------------------------
    # Chat input
    # -----------------------------------------------------------------------

    question = st.chat_input(
        "Ask something about the ingested documents"
    )

    if question:

        if not workspace_id.strip() or not role_ids:
            st.error(
                "Select a workspace and at least one allowed role first."
            )

        else:
            # ---------------------------------------------------------------
            # Add user message
            # ---------------------------------------------------------------

            user_message = {
                "role": "user",
                "content": question,
            }

            st.session_state.messages.append(user_message)

            # Keep the temporary chat object synchronized.
            st.session_state.chats[
                st.session_state.thread_id
            ]["messages"] = st.session_state.messages

            # Give the chat a useful temporary title.
            update_chat_title(
                st.session_state.thread_id,
                question,
            )

            # ---------------------------------------------------------------
            # Render user message
            # ---------------------------------------------------------------

            with st.chat_message("user"):
                st.markdown(question)

            # ---------------------------------------------------------------
            # Ask API
            # ---------------------------------------------------------------

            with st.chat_message("assistant"):

                with st.spinner(
                    "Searching and synthesizing..."
                ):

                    try:
                        result = request_json(
                            "POST",
                            "/api/chat/",
                            json={
                                "message": question,
                                "thread_id": st.session_state.thread_id,
                                "workspace_id": workspace_id.strip(),
                                "allowed_role_ids": role_ids,
                                "session_history": (
                                    st.session_state.messages[:-1]
                                ),
                            },
                        )

                        response_text = result.get(
                            "response",
                            "No answer returned.",
                        )

                        st.markdown(response_text)

                        confidence = result.get("confidence")

                        confidence_label = (
                            f"{confidence:.2f}"
                            if confidence is not None
                            else "n/a"
                        )

                        st.caption(
                            f"{result.get('model_used', 'unknown')} | "
                            f"{result.get('processing_time', 0):.2f}s | "
                            f"confidence {confidence_label}"
                        )

                        for citation in result.get(
                            "citations",
                            [],
                        ):

                            st.markdown(
                                f"""
                                <div class='citation'>
                                    <b>
                                        {
                                            citation.get("filename")
                                            or citation.get(
                                                "file_id",
                                                "source",
                                            )
                                        }
                                    </b>
                                    |
                                    chunk {
                                        citation.get("chunk_id", "")
                                    }
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                        # ---------------------------------------------------
                        # Save assistant message to temporary chat
                        # ---------------------------------------------------

                        assistant_message = {
                            "role": "assistant",
                            "content": response_text,
                            "meta": result,
                        }

                        st.session_state.messages.append(
                            assistant_message
                        )

                        st.session_state.chats[
                            st.session_state.thread_id
                        ]["messages"] = (
                            st.session_state.messages
                        )

                    except (httpx.HTTPError, ValueError) as exc:

                        st.error(error_message(exc))

                        # Remove user message if API request failed.
                        st.session_state.messages.pop()

                        st.session_state.chats[
                            st.session_state.thread_id
                        ]["messages"] = (
                            st.session_state.messages
                        )
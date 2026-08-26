import os
from typing import Any

import requests
import streamlit as st
from typing import TypedDict


class DemoUser(TypedDict):
    id: str
    email: str
    display_name: str
    workspace_id: str
    role: str

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="InquireAI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONFIG
# ============================================================

API_BASE_URL = os.getenv(
    "INQUIREAI_API_URL",
    "http://localhost:8000",
)

REQUEST_TIMEOUT = 30
CHAT_TIMEOUT = 300
UPLOAD_TIMEOUT = 600


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 1rem;
            max-width: 1200px;
        }

        .app-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0;
        }

        .app-subtitle {
            color: #808080;
            margin-top: 0.2rem;
        }

        .user-card {
            padding: 1rem;
            border-radius: 10px;
            border: 1px solid rgba(128, 128, 128, 0.25);
            margin-bottom: 1rem;
        }

        .metadata-card {
            padding: 0.8rem;
            border-radius: 8px;
            border: 1px solid rgba(128, 128, 128, 0.2);
            margin-top: 0.5rem;
        }

        [data-testid="stSidebar"] {
            min-width: 320px;
            max-width: 320px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

def initialize_state() -> None:
    defaults = {
        "users": [],
        "roles": [],
        "selected_user_email": None,
        "selected_user": None,
        "selected_role": None,
        "workspace_id": None,
        "conversations": [],
        "active_thread_id": None,
        "messages": [],
        "api_available": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ============================================================
# HTTP HELPERS
# ============================================================

def extract_error(response: requests.Response) -> str:
    try:
        data = response.json()

        if isinstance(data, dict):
            return str(
                data.get("detail")
                or data.get("message")
                or data
            )

        return str(data)

    except Exception:
        return response.text or f"HTTP {response.status_code}"


def get_json(
    path: str,
    params: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> Any:

    response = requests.get(
        f"{API_BASE_URL}{path}",
        params=params,
        timeout=timeout,
    )

    if not response.ok:
        raise RuntimeError(extract_error(response))

    return response.json()


def post_json(
    path: str,
    payload: dict,
    timeout: int = REQUEST_TIMEOUT,
) -> Any:

    response = requests.post(
        f"{API_BASE_URL}{path}",
        json=payload,
        timeout=timeout,
    )

    if not response.ok:
        raise RuntimeError(extract_error(response))

    return response.json()


def patch_json(
    path: str,
    payload: dict,
    params: dict | None = None,
) -> Any:

    response = requests.patch(
        f"{API_BASE_URL}{path}",
        json=payload,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(extract_error(response))

    return response.json()


def delete_request(
    path: str,
    params: dict | None = None,
) -> None:

    response = requests.delete(
        f"{API_BASE_URL}{path}",
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(extract_error(response))


# ============================================================
# API FUNCTIONS
# ============================================================

@st.cache_data(ttl=60)
def fetch_users() -> list[dict]:
    """
    Current backend endpoint:

    router prefix: /api/users
    route: /users

    Final endpoint:
    /api/users/users
    """

    return get_json("/api/users/users")


@st.cache_data(ttl=60)
def fetch_roles() -> list[str]:
    """
    Current backend endpoint:
    /api/users/roles
    """

    return get_json("/api/users/roles")


def fetch_conversations(
    workspace_id: str,
    user_email: str,
) -> list[dict]:

    return get_json(
        "/api/conversations",
        params={
            "workspace_id": workspace_id,
            "user_email": user_email,
        },
    )


def fetch_messages(
    thread_id: str,
    workspace_id: str,
    user_email: str,
) -> list[dict]:

    return get_json(
        f"/api/conversations/{thread_id}/messages",
        params={
            "workspace_id": workspace_id,
            "user_email": user_email,
        },
    )


def create_conversation(
    workspace_id: str,
    user_email: str,
) -> dict:

    return post_json(
        "/api/conversations",
        {
            "workspace_id": workspace_id,
            "user_email": user_email,
            "title": "New conversation",
        },
    )


def rename_conversation(
    thread_id: str,
    user_email: str,
    title: str,
) -> dict:

    return patch_json(
        f"/api/conversations/{thread_id}",
        {
            "title": title,
        },
        params={
            "user_email": user_email,
        },
    )


def delete_conversation(
    thread_id: str,
    user_email: str,
) -> None:

    delete_request(
        f"/api/conversations/{thread_id}",
        params={
            "user_email": user_email,
        },
    )


def send_chat_message(
    message: str,
    user_email: str,
    workspace_id: str,
    thread_id: str | None,
) -> dict:

    payload = {
        "message": message,
        "user_email": user_email,
        "workspace_id": workspace_id,
        "thread_id": thread_id,
    }

    return post_json(
        "/api/chat/",
        payload,
        timeout=CHAT_TIMEOUT,
    )


def upload_document(
    uploaded_file,
    workspace_id: str,
    user_email: str,
    allowed_roles: list[str],
) -> dict:

    files = {
        "file": (
            uploaded_file.name,
            uploaded_file.getvalue(),
            uploaded_file.type
            or "application/octet-stream",
        )
    }

    data = {
        "workspace_id": workspace_id,
        "user_email": user_email,
        "allowed_role_ids": ",".join(allowed_roles),
    }

    response = requests.post(
        f"{API_BASE_URL}/files",
        files=files,
        data=data,
        timeout=UPLOAD_TIMEOUT,
    )

    if not response.ok:
        raise RuntimeError(extract_error(response))

    return response.json()


# ============================================================
# STATE FUNCTIONS
# ============================================================

def get_current_user() -> dict | None:

    email = st.session_state.selected_user_email

    if not email:
        return None

    for user in st.session_state.users:
        if user["email"] == email:
            return user

    return None


def refresh_conversations() -> DemoUser | None:

    user = get_current_user()

    if not user:
        st.session_state.conversations = []
        return

    workspace_id = str(
        user["workspace_id"]
    )

    conversations = fetch_conversations(
        workspace_id=workspace_id,
        user_email=user["email"],
    )

    st.session_state.conversations = conversations


def select_user(user: dict) -> None:

    current_email = (
        st.session_state.selected_user_email
    )

    if current_email == user["email"]:
        return

    st.session_state.selected_user_email = (
        user["email"]
    )

    st.session_state.selected_user = user

    st.session_state.selected_role = (
        user["role"]
    )

    st.session_state.workspace_id = str(
        user["workspace_id"]
    )

    st.session_state.active_thread_id = None

    st.session_state.messages = []

    st.session_state.conversations = []

    try:
        refresh_conversations()
    except Exception:
        pass


def open_conversation(
    thread_id: str,
) -> None:

    user = get_current_user()

    if not user:
        return

    messages = fetch_messages(
        thread_id=thread_id,
        workspace_id=str(user["workspace_id"]),
        user_email=user["email"],
    )

    st.session_state.active_thread_id = (
        thread_id
    )

    st.session_state.messages = messages


def start_new_chat() -> None:

    st.session_state.active_thread_id = None

    st.session_state.messages = []


# ============================================================
# LOAD USERS
# ============================================================

try:

    if not st.session_state.users:

        st.session_state.users = (
            fetch_users()
        )

    if not st.session_state.roles:

        st.session_state.roles = (
            fetch_roles()
        )

    st.session_state.api_available = True

except Exception as exc:

    st.session_state.api_available = False

    st.error(
        "Unable to connect to the InquireAI backend."
    )

    st.code(
        API_BASE_URL
    )

    st.exception(exc)

    st.stop()


# ============================================================
# INITIAL USER
# ============================================================

if (
    st.session_state.selected_user_email is None
    and st.session_state.users
):

    first_user = st.session_state.users[0]

    st.session_state.selected_user_email = (
        first_user["email"]
    )

    st.session_state.selected_user = (
        first_user
    )

    st.session_state.selected_role = (
        first_user["role"]
    )

    st.session_state.workspace_id = str(
        first_user["workspace_id"]
    )

    try:
        refresh_conversations()
    except Exception:
        pass


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🤖 InquireAI")

    st.caption(
        "Enterprise AI Knowledge Assistant"
    )

    st.divider()

    # --------------------------------------------------------
    # USER SELECTION
    # --------------------------------------------------------

    st.subheader("Demo Context")

    users = st.session_state.users

    user_labels = {
        user["email"]: (
            f"{user['display_name']} "
            f"({user['role']})"
        )
        for user in users
    }

    user_emails = list(
        user_labels.keys()
    )

    current_index = 0

    if (
        st.session_state.selected_user_email
        in user_emails
    ):

        current_index = user_emails.index(
            st.session_state.selected_user_email
        )

    selected_email = st.selectbox(
        "Select User",
        options=user_emails,
        index=current_index,
        format_func=lambda email: user_labels[email],
    )

    if (
        selected_email
        != st.session_state.selected_user_email
    ):

        selected_user = next(
            user
            for user in users
            if user["email"] == selected_email
        )

        select_user(selected_user)

        st.rerun()

    current_user = get_current_user() or None

    if current_user:

        # ----------------------------------------------------
        # ROLE DISPLAY
        # ----------------------------------------------------

        st.selectbox(
            "Role",
            options=st.session_state.roles,
            index=st.session_state.roles.index(
                current_user["role"]
            )
            if current_user["role"]
            in st.session_state.roles
            else 0,
            disabled=True,
        )

        st.caption(
            "Role is resolved server-side "
            "from the selected user."
        )

        # ----------------------------------------------------
        # USER INFORMATION
        # ----------------------------------------------------

        st.markdown(
            f"""
            <div class="user-card">
                <b>User</b><br>
                {current_user["display_name"]}<br><br>

                <b>Email</b><br>
                {current_user["email"]}<br><br>

                <b>Workspace</b><br>
                <code>{current_user["workspace_id"]}</code>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()

    # --------------------------------------------------------
    # NEW CHAT
    # --------------------------------------------------------

    if st.button(
        "➕ New Chat",
        use_container_width=True,
        type="primary",
    ):

        start_new_chat()

        st.rerun()

    st.divider()

    # --------------------------------------------------------
    # CONVERSATIONS
    # --------------------------------------------------------

    col1, col2 = st.columns(
        [4, 1]
    )

    with col1:
        st.subheader(
            "Conversations"
        )

    with col2:

        if st.button(
            "↻",
            help="Refresh conversations",
        ):

            try:

                refresh_conversations()

                st.rerun()

            except Exception as exc:

                st.error(str(exc))

    conversations = (
        st.session_state.conversations
    )

    if not conversations:

        st.caption(
            "No conversations yet."
        )

    else:

        for conversation in conversations:

            thread_id = str(
                conversation["id"]
            )

            title = (
                conversation.get("title")
                or "New conversation"
            )

            active = (
                thread_id
                == st.session_state.active_thread_id
            )

            button_type = (
                "primary"
                if active
                else "secondary"
            )

            conversation_col, menu_col = (
                st.columns([5, 1])
            )

            with conversation_col:

                if st.button(
                    title,
                    key=f"conversation_{thread_id}",
                    use_container_width=True,
                    type=button_type,
                ):

                    try:

                        open_conversation(
                            thread_id
                        )

                        st.rerun()

                    except Exception as exc:

                        st.error(
                            f"Failed to load conversation: "
                            f"{exc}"
                        )

            with menu_col:

                with st.popover(
                    "⋮",
                    use_container_width=True,
                ):

                    new_title = st.text_input(
                        "Rename",
                        value=title,
                        key=f"rename_input_{thread_id}",
                    )

                    if st.button(
                        "Save",
                        key=f"rename_save_{thread_id}",
                    ):

                        try:

                            rename_conversation(
                                thread_id=thread_id,
                                user_email=current_user[
                                    "email"
                                ],
                                title=new_title,
                            )

                            refresh_conversations()

                            st.rerun()

                        except Exception as exc:

                            st.error(str(exc))

                    st.divider()

                    if st.button(
                        "Delete",
                        key=f"delete_{thread_id}",
                    ):

                        try:

                            delete_conversation(
                                thread_id=thread_id,
                                user_email=current_user[
                                    "email"
                                ],
                            )

                            if (
                                st.session_state.active_thread_id
                                == thread_id
                            ):

                                start_new_chat()

                            refresh_conversations()

                            st.rerun()

                        except Exception as exc:

                            st.error(str(exc))


current_user = get_current_user()

if current_user is None:

    st.warning("No demo user selected.")
    st.stop()

assert current_user is not None


st.markdown(
    """
    <div class="app-title">
        InquireAI
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="app-subtitle">
        Enterprise RAG Assistant
        &nbsp; • &nbsp;
        {current_user["display_name"]}
        &nbsp; • &nbsp;
        {current_user["role"]}
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# ADMIN DOCUMENT INGESTION
# ============================================================

if current_user["role"] == "admin":

    with st.expander(
        "📄 Document Ingestion",
        expanded=False,
    ):

        st.write(
            "Upload a document to the workspace "
            "knowledge base."
        )

        uploaded_file = st.file_uploader(
            "Choose a file",
            type=[
                "pdf",
                "docx",
                "txt",
                "csv",
                "xlsx",
            ],
        )

        st.caption(
            "Select which roles can retrieve "
            "information from this document."
        )

        allowed_roles = st.multiselect(
            "Allowed Roles",
            options=st.session_state.roles,
            default=["admin"]
            if "admin"
            in st.session_state.roles
            else [],
        )

        if st.button(
            "🚀 Ingest Document",
            disabled=uploaded_file is None,
            type="primary",
        ):

            if not allowed_roles:

                st.warning(
                    "Select at least one role."
                )

            else:

                try:

                    with st.spinner(
                        "Running document ingestion pipeline..."
                    ):

                        result = upload_document(
                            uploaded_file=uploaded_file,
                            workspace_id=str(
                                current_user[
                                    "workspace_id"
                                ]
                            ),
                            user_email=current_user[
                                "email"
                            ],
                            allowed_roles=allowed_roles,
                        )

                    st.success(
                        "Document ingested successfully."
                    )

                    metric1, metric2 = st.columns(
                        2
                    )

                    metric1.metric(
                        "Chunks Stored",
                        result.get(
                            "chunks_stored",
                            0,
                        ),
                    )

                    metric2.metric(
                        "Status",
                        result.get(
                            "status",
                            "success",
                        ),
                    )

                    st.caption(
                        f"File ID: "
                        f"`{result.get('file_id')}`"
                    )

                except Exception as exc:

                    st.error(
                        f"Ingestion failed: {exc}"
                    )


# ============================================================
# CHAT HEADER
# ============================================================

st.divider()

header_col1, header_col2 = st.columns(
    [4, 1]
)

with header_col1:

    if st.session_state.active_thread_id:

        active_conversation = next(
            (
                conversation
                for conversation
                in st.session_state.conversations
                if str(conversation["id"])
                == st.session_state.active_thread_id
            ),
            None,
        )

        conversation_title = (
            active_conversation.get(
                "title",
                "Conversation",
            )
            if active_conversation
            else "Conversation"
        )

        st.subheader(
            conversation_title
        )

    else:

        st.subheader(
            "New Conversation"
        )


with header_col2:

    if st.session_state.active_thread_id:

        st.caption(
            f"Thread: "
            f"`{st.session_state.active_thread_id[:8]}`"
        )


# ============================================================
# CHAT MESSAGES
# ============================================================

if not st.session_state.messages:

    st.markdown(
        """
        ### How can I help you?

        Ask questions about documents available
        in your workspace.

        Your role determines which documents
        and chunks are available to the RAG
        retrieval pipeline.
        """
    )


for message in st.session_state.messages:

    role = message.get(
        "role",
        "assistant",
    )

    content = message.get(
        "content",
        "",
    )

    if role not in [
        "user",
        "assistant",
    ]:
        role = "assistant"

    with st.chat_message(role):

        st.markdown(content)

        # ----------------------------------------------------
        # ASSISTANT METADATA
        # ----------------------------------------------------

        if role == "assistant":

            metadata = (
                message.get("metadata")
                or {}
            )

            confidence = (
                metadata.get("confidence")
            )

            citations = (
                metadata.get("citations")
                or []
            )

            model_used = (
                metadata.get("model_used")
            )

            abstained = (
                metadata.get("abstained")
            )

            if (
                confidence is not None
                or citations
                or model_used
                or abstained
            ):

                with st.expander(
                    "Response Details"
                ):

                    if confidence is not None:

                        try:

                            st.metric(
                                "Confidence",
                                f"{float(confidence):.2f}",
                            )

                        except (
                            TypeError,
                            ValueError,
                        ):

                            st.write(
                                f"Confidence: "
                                f"{confidence}"
                            )

                    if model_used:

                        st.caption(
                            f"Model: "
                            f"`{model_used}`"
                        )

                    if abstained:

                        st.warning(
                            "The assistant abstained "
                            "due to insufficient "
                            "grounded evidence."
                        )

                    if citations:

                        st.markdown(
                            "#### Sources"
                        )

                        for index, citation in enumerate(
                            citations,
                            start=1,
                        ):

                            if isinstance(
                                citation,
                                dict,
                            ):

                                filename = (
                                    citation.get(
                                        "filename"
                                    )
                                    or citation.get(
                                        "source"
                                    )
                                    or citation.get(
                                        "document_name"
                                    )
                                    or "Document"
                                )

                                page = (
                                    citation.get(
                                        "page_number"
                                    )
                                    or citation.get(
                                        "page"
                                    )
                                )

                                chunk_id = (
                                    citation.get(
                                        "chunk_id"
                                    )
                                )

                                source_text = (
                                    f"**{index}. {filename}**"
                                )

                                if page:
                                    source_text += (
                                        f" — Page {page}"
                                    )

                                if chunk_id:
                                    source_text += (
                                        f" — Chunk `{chunk_id}`"
                                    )

                                st.markdown(
                                    source_text
                                )

                            else:

                                st.markdown(
                                    f"{index}. {citation}"
                                )


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask InquireAI anything about your documents..."
)


if prompt:

    # --------------------------------------------------------
    # IMMEDIATELY DISPLAY USER MESSAGE
    # --------------------------------------------------------

    with st.chat_message("user"):

        st.markdown(prompt)

    # --------------------------------------------------------
    # CALL BACKEND
    # --------------------------------------------------------

    try:

        with st.chat_message("assistant"):

            with st.spinner(
                "InquireAI is reasoning..."
            ):

                result = send_chat_message(
                    message=prompt,
                    user_email=current_user[
                        "email"
                    ],
                    workspace_id=str(
                        current_user[
                            "workspace_id"
                        ]
                    ),
                    thread_id=st.session_state.active_thread_id,
                )

            response = result.get(
                "response"
            ) or "No response generated."

            st.markdown(response)

            # ------------------------------------------------
            # RESPONSE DETAILS
            # ------------------------------------------------

            confidence = result.get(
                "confidence"
            )

            citations = result.get(
                "citations",
                [],
            )

            model_used = result.get(
                "model_used"
            )

            abstained = result.get(
                "abstained",
                False,
            )

            if (
                confidence is not None
                or citations
                or model_used
                or abstained
            ):

                with st.expander(
                    "Response Details"
                ):

                    if confidence is not None:

                        try:

                            st.metric(
                                "Confidence",
                                f"{float(confidence):.2f}",
                            )

                        except (
                            TypeError,
                            ValueError,
                        ):

                            st.write(
                                f"Confidence: "
                                f"{confidence}"
                            )

                    if model_used:

                        st.caption(
                            f"Model: "
                            f"`{model_used}`"
                        )

                    if abstained:

                        st.warning(
                            "Insufficient grounded evidence."
                        )

                    if citations:

                        st.markdown(
                            "#### Sources"
                        )

                        for index, citation in enumerate(
                            citations,
                            start=1,
                        ):

                            if isinstance(
                                citation,
                                dict,
                            ):

                                filename = (
                                    citation.get(
                                        "filename"
                                    )
                                    or citation.get(
                                        "source"
                                    )
                                    or "Document"
                                )

                                page = (
                                    citation.get(
                                        "page_number"
                                    )
                                    or citation.get(
                                        "page"
                                    )
                                )

                                text = (
                                    f"**{index}. {filename}**"
                                )

                                if page:
                                    text += (
                                        f" — Page {page}"
                                    )

                                st.markdown(text)

                            else:

                                st.markdown(
                                    f"{index}. {citation}"
                                )

    except Exception as exc:

        st.error(
            f"Chat request failed: {exc}"
        )

        st.stop()

    # --------------------------------------------------------
    # UPDATE THREAD
    # --------------------------------------------------------

    new_thread_id = result.get(
        "thread_id"
    )

    if new_thread_id:

        st.session_state.active_thread_id = (
            new_thread_id
        )

    # --------------------------------------------------------
    # UPDATE LOCAL MESSAGES
    # --------------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
            "metadata": None,
        }
    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response,
            "metadata": {
                "confidence": confidence,
                "citations": citations,
                "model_used": model_used,
                "abstained": abstained,
            },
        }
    )

    # --------------------------------------------------------
    # REFRESH CONVERSATIONS
    # --------------------------------------------------------

    try:

        refresh_conversations()

    except Exception:
        pass

    st.rerun()
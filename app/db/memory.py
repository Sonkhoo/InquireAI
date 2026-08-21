import uuid
from psycopg.types.json import Json
from app.config import get_settings
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

settings = get_settings()

# check= validates a connection is alive before handing it out, so
# connections killed by a DB restart are discarded instead of raising
# "Software caused connection abort" on the client.
pool = ConnectionPool(
    conninfo=settings.db_url,
    max_size=settings.DB_POOL_SIZE,
    kwargs={"connect_timeout": 5, "row_factory": dict_row},
    check=ConnectionPool.check_connection,
)

# Block until Postgres is reachable instead of serving requests with
# a dead pool (e.g. when the API starts before docker compose is up).
pool.open(wait=True, timeout=30)


# STM (Short Term Memory) for conversations

def create_conversation(id: str, user_id: str, workspace_id: str, title: str) -> uuid.UUID | None:
    """Create a new conversation and return its ID."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "insert into conversations (id, user_id, workspace_id, title) values (%s, %s, %s, %s) "
            "on conflict(id) do nothing "
            "returning id",
            (uuid.UUID(id), uuid.UUID(user_id), uuid.UUID(workspace_id), title)
        )
    row = cursor.fetchone()
    if row:
        return row["id"]
    else:
        return None  # Conversation already exists, return None or handle as needed

def get_conversation(user_id: str, workspace_id: str, thread_id: str, limit: int | None = None)-> list[dict]:
    """Retrieve a conversation by user_id, workspace_id, and thread_id."""
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be a positive integer or None.")
    if limit is None:
        limit = settings.STM_MAX_MESSAGES

    with pool.connection() as conn:
        cursor = conn.execute(
            "select m.id, m.content, m.role, m.metadata from messages m "
            "join conversations c on c.id = m.conversation_id "
            "where c.user_id = %s and c.workspace_id = %s and c.id = %s "
            "limit %s",
            (user_id, workspace_id, thread_id, limit)
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def add_message(conversation_id: str, role: str, content: str, metadata: dict | None = None) -> uuid.UUID:
    """Add a message to a conversation and return the message ID."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "insert into messages (conversation_id, role, content, metadata) "
            "values (%s, %s, %s, %s) returning id",
            (conversation_id, role, content, Json(metadata) if metadata is not None else None)
        )
    row = cursor.fetchone()
    if row:
        return row["id"]
    else:
        raise Exception("Failed to add message to the conversation.")

def get_all_conversations(user_id: str, workspace_id: str) -> list[dict]:
    """Retrieve all conversations for a given user and workspace."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "select id, title from conversations where user_id = %s and workspace_id = %s "
            "order by updated_at desc nulls last",
            (user_id, workspace_id)
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def rename_conversation(thread_id: str, user_id: str, title: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "update conversations set title = %s "
            "where id = %s and user_id = %s",
            (title, uuid.UUID(thread_id), uuid.UUID(user_id)),
        )

def delete_conversation(thread_id: str, user_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "delete from conversations where id = %s and user_id = %s",
            (uuid.UUID(thread_id), uuid.UUID(user_id)),
        )
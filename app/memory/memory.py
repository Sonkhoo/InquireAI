import uuid
from psycopg.types.json import Json
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

settings = get_settings()

pool = ConnectionPool(
    conninfo=settings.db_url,
    max_size=settings.DB_POOL_SIZE,
    kwargs={"connect_timeout": 5, "row_factory": dict_row},
    check=ConnectionPool.check_connection,
    open=False,
)

def open_pool() -> None:
    pool.open(wait=True, timeout=30)

def close_pool() -> None:
    pool.close()

# Demo users (auth is skipped)

def get_user_by_email(email: str) -> dict | None:
    """Look up a demo user by email. Returns {id, email, display_name, role} or None."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "select id, email, display_name, role from users where email = %s",
            (email,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None

def get_user(user_id: str) -> dict | None:
    """Look up a demo user by ID."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "select id, email, display_name, workspace_id, role "
            "from users where id = %s",
            (user_id,),
        )
        row = cursor.fetchone()
    return dict(row) if row else None

def get_all_users() -> list[dict]:
    """Retrieve all demo users."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "select id, email, display_name, workspace_id, role from users"
        )
        rows = cursor.fetchall()
    return [dict(row) for row in rows]

def create_conversation(id: str, user_id: str, workspace_id: str, title: str) -> uuid.UUID | None:
    """Create a new conversation and return its ID."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "insert into conversations (id, user_id, workspace_id, title) values (%s, %s, %s, %s) "
            "on conflict(id) do nothing "
            "returning id",
            (id, user_id, workspace_id, title)
        )
        row = cursor.fetchone()
    return row["id"] if row else None

def get_conversation(user_id: str, workspace_id: str, thread_id: str, limit: int | None = None) -> list[dict]:
    """Retrieve a conversation history chronologically."""
    if limit is not None and limit <= 0:
        raise ValueError("Limit must be a positive integer or None.")

    with pool.connection() as conn:
        if limit is None:
            cursor = conn.execute(
                "select m.id, m.content, m.role, m.metadata from messages m "
                "join conversations c on c.id = m.conversation_id "
                "where c.user_id = %s and c.workspace_id = %s and c.id = %s "
                "order by m.created_at asc",
                (user_id, workspace_id, thread_id)
            )
            return [dict(row) for row in cursor.fetchall()]
        else:
            # Fetch the most recent N messages, then reverse to display chronologically
            cursor = conn.execute(
                "select m.id, m.content, m.role, m.metadata from messages m "
                "join conversations c on c.id = m.conversation_id "
                "where c.user_id = %s and c.workspace_id = %s and c.id = %s "
                "order by m.created_at desc "
                "limit %s",
                (user_id, workspace_id, thread_id, limit)
            )
            rows = cursor.fetchall()
            messages = [dict(row) for row in rows]
            messages.reverse()
            return messages

def add_message(conversation_id: str, role: str, content: str, metadata: dict | None = None) -> uuid.UUID:
    """Add a message to a conversation and return the message ID."""
    with pool.connection() as conn:
        cursor = conn.execute(
            "insert into messages (conversation_id, role, content, metadata) "
            "values (%s, %s, %s, %s) returning id",
            (
                uuid.UUID(conversation_id),
                role,
                content,
                Json(metadata) if metadata is not None else None
            )
        )
        row = cursor.fetchone()
    
    if row:
        return row["id"]
    raise RuntimeError("Failed to add message to the conversation.")

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
            (title, thread_id, user_id),
        )

def delete_conversation(thread_id: str, user_id: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "delete from conversations where id = %s and user_id = %s",
            (thread_id, user_id),
        )

def conversation_belongs_to_user(
    thread_id: str,
    user_id: str,
    workspace_id: str,
) -> bool:
    with pool.connection() as conn:
        row = conn.execute(
            """
            select 1
            from conversations
            where id = %s
              and user_id = %s
              and workspace_id = %s
            """,
            (thread_id, user_id, workspace_id),
        ).fetchone()

    return row is not None
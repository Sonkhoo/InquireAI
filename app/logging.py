from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import logfire


def init_logging() -> None:
    """Initialize Logfire once for the current Python process."""
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    logfire.configure(
        send_to_logfire=True,
        service_name="ai-service",
        environment=os.getenv("APP_ENV", "development"),
    )

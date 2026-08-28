from __future__ import annotations
import os
import sys
from pathlib import Path

from app.logging import init_logging

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

init_logging()

# Redirect Hugging Face cache to the project directory (D: drive) to avoid C: drive space limits
os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))

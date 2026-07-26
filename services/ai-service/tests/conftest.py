from __future__ import annotations
from dotenv import load_dotenv

import os
import sys
from pathlib import Path


# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if "HF_API_KEY" in os.environ and "HF_TOKEN" not in os.environ:
    os.environ["HF_TOKEN"] = os.environ["HF_API_KEY"]
    
# Redirect Hugging Face cache to the project directory (D: drive) to avoid C: drive space limits
os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / ".cache" / "huggingface"))

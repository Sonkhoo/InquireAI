"""
Cleaning utilities for text processing.
Security -
1. Html/xml tags are removed
2. Scripts and styles are removed
3. Prompt injection is removed (done)
Cleaning -
1. Unicode NFC
2. Collapse whitespace
3. Remove blank lines
4. etc
"""

import re
from typing import List, Dict
import unicodedata

from cv2 import threshold
from app.logging import init_logging
from app.models import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from app.logging import logfire

HTML_PATTERNS = [
    r"<html.*?>",
    r"<body.*?>",
    r"<div.*?>",
    r"<script.*?>",
    r"<style.*?>",
    r"<iframe.*?>",
    r"<img.*?>",
]

XML_PATTERNS = [
    r"<\?xml",
    r"<!DOCTYPE",
    r"<!ENTITY",
]

    
def clean_text(text: str) -> str:
    # HTML
    for pattern in HTML_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.I | re.S)

    # XML
    for pattern in XML_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.I | re.S)

    # Unicode normalization
    text = unicodedata.normalize("NFC", text)

    # Remove zero-width characters
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)

    # Collapse repeated blank lines
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()

def strip_base64_from_text(text: str) -> str:
    """
    Remove base64-encoded blobs from the text.
    """
    base64_pattern = re.compile(
        r'(?:data:[a-zA-Z\-]+/[a-zA-Z\-+.]+;base64,)?[A-Za-z0-9+/]{100,}=*'
    )
    return base64_pattern.sub("[IMAGE_BLOB_REMOVED]", text)
"""
Text cleaning and security utilities.
Cleaning:
- Unicode NFC normalization
- Normalize line endings
- Remove zero-width/invisible characters
- Remove control characters
- Collapse whitespace
- Collapse excessive blank lines

Security:
- Detect Base64/encoded blobs
- Detect suspicious URLs
- Detect oversized/invalid chunks
- Detect unusually long tokens
"""

import hashlib
import re
import unicodedata
from urllib.parse import urlparse
from app.logging import logfire


# Configurable thresholds
MIN_CHUNK_LENGTH = 50
MAX_CHUNK_LENGTH = 20_000
MAX_URL_LENGTH = 2_000
MAX_TOKEN_LENGTH = 200
MIN_BASE64_LENGTH = 100

# Text Cleaning Utilities

ZERO_WIDTH_CHARS = {
    "\u200b",  # Zero Width Space
    "\u200c",  # Zero Width Non-Joiner
    "\u200d",  # Zero Width Joiner
    "\ufeff",  # Zero Width No-Break Space / BOM
    "\u2060",  # Word Joiner
}

# Clean text function
def clean_text(text: str) -> str:
    """
    Clean extracted text from PDF/DOCX/XLSX.

    This function only performs text normalization.
    Format-specific security such as PDF parser safety,
    ZIP limits, and XML/XXE protection should be handled
    by the document parser.
    """

    if not text:
        return ""

    # Unicode normalization
    text = unicodedata.normalize("NFC", text)

    # Normalize line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove zero-width / invisible characters
    text = "".join(
        char for char in text
        if char not in ZERO_WIDTH_CHARS
    )

    # Remove control characters except newline and tab
    text = "".join(
        char
        for char in text
        if (
            char in "\n\t"
            or unicodedata.category(char) != "Cc"
        )
    )

    # Collapse spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive blank lines
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)

    return text.strip()

# Base 64 / Encoded Blob Detection
BASE64_PATTERN = re.compile(
    rf"""
    (?:
        data:[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+;base64,
    )?
    [A-Za-z0-9+/]{{{MIN_BASE64_LENGTH},}}
    ={{0,2}}
    """,
    re.VERBOSE,
)


def contains_base64(text: str) -> bool:
    """
    Detect large Base64-like blobs.

    Returns True if an encoded blob is found.
    """

    return bool(BASE64_PATTERN.search(text))


# Suspicious URL Detection

URL_PATTERN = re.compile(
    r"""
    https?://[^\s<>"']+
    |
    javascript:[^\s<>"']+
    |
    data:[^\s<>"']+
    |
    vbscript:[^\s<>"']+
    """,
    re.IGNORECASE | re.VERBOSE,
)

DANGEROUS_SCHEMES = {
    "javascript",
    "data",
    "vbscript",
}


def contains_suspicious_url(text: str) -> bool:
    """
    Detect dangerous URL schemes or unusually long URLs.
    """

    for url in URL_PATTERN.findall(text):
        parsed = urlparse(url)

        if parsed.scheme.lower() in DANGEROUS_SCHEMES:
            return True

        if len(url) > MAX_URL_LENGTH:
            return True

    return False


# Chunk Sanity Checks
def is_valid_chunk(text: str) -> bool:
    """
    Basic sanity check for a chunk.

    Rejects:
    - empty chunks
    - very small chunks
    - excessively large chunks
    - chunks with almost no alphanumeric content
    """

    text = text.strip()

    if not text:
        return False

    if len(text) < MIN_CHUNK_LENGTH:
        return False

    if len(text) > MAX_CHUNK_LENGTH:
        return False

    alphanumeric_count = sum(
        char.isalnum()
        for char in text
    )

    return alphanumeric_count >= 10

# Check for unusually long tokens
def contains_long_token(text: str) -> bool:
    """
    Detect unusually long whitespace-separated tokens.

    Useful for catching malformed extraction or encoded data.
    """

    return any(
        len(token) > MAX_TOKEN_LENGTH
        for token in text.split()
    )


# Checksum / Hashing Utilities
def get_text_hash(text: str) -> str:
    """
    Return a stable hash for duplicate detection.
    """

    normalized = text.strip().lower()

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


# Combined chunk safety check
def is_safe_chunk(text: str) -> bool:
    """
    Run lightweight security/sanity checks on a chunk.

    Prompt injection is intentionally NOT checked here because
    it is handled separately by detect_prompt_injection().
    """

    if not is_valid_chunk(text):
        return False

    if contains_base64(text):
        logfire.warning(
            "Encoded blob detected in chunk",
            text_length=len(text),
        )
        return False

    if contains_suspicious_url(text):
        logfire.warning(
            "Suspicious URL detected in chunk",
            text_length=len(text),
        )
        return False

    if contains_long_token(text):
        logfire.warning(
            "Unusually long token detected in chunk",
            text_length=len(text),
        )
        return False

    return True
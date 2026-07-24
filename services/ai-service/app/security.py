"""
Security and PII Handling for the AI Service.
"""

import re
from typing import Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langsmith import traceable
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

#Input sanitization regex patterns
EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_REGEX = r"^\+?1?-?\.?\s?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})$"
IP_ADDRESS_REGEX = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"

class SanitizedRequest(BaseModel):
    """
    Model for sanitized requests.
    """
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?previous",
        r"new\s+instructions:",
        r"system\s*prompt",
        r"---\s*end\s*(of)?\s*prompt",
        r"pretend\s+you\s+are",
        r"act\s+as\s+(if\s+)?you",
        r"bypass\s+(all\s+)?restrictions",
    ]

    def __init__(self):
        self.patterns = self._compile_patterns()

    def _compile_patterns(self):
        """Compile injection patterns once during initialization."""
        compiled_patterns = []
        for pattern in self.INJECTION_PATTERNS:
            compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
        return compiled_patterns

    def is_suspicious(self, text: str) -> tuple[bool, Optional[str]]:
        """Check if input contains suspicious patterns."""
        for pattern in self.patterns:
            if pattern.search(text):
                return True, f"Suspicious pattern detected: {pattern.pattern}"
        return False, None

    def sanitize(self, text: str) -> str:
        """Remove potentially dangerous content."""
        # Remove common injection delimiters
        text = re.sub(r"[-]{3,}", "", text)
        text = re.sub(r"[=]{3,}", "", text)

        # Escape special characters that might confuse the model
        text = text.replace("{{", "{ {").replace("}}", "} }")

        return text.strip()

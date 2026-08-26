"""

PII detection and anonymization using Microsoft Presidio.

"""

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine


@lru_cache(maxsize=1)
def get_analyzer() -> AnalyzerEngine:
    """Create and cache the Presidio analyzer."""
    return AnalyzerEngine()


@lru_cache(maxsize=1)
def get_anonymizer() -> AnonymizerEngine:
    """Create and cache the Presidio anonymizer."""
    return AnonymizerEngine()


def detect_pii(text: str) -> bool:
    """
    Return True when Presidio detects PII in the text.
    """
    if not text.strip():
        return False

    analyzer = get_analyzer()

    results = analyzer.analyze(
        text=text,
        language="en",
    )

    return bool(results)


def anonymize_pii(text: str) -> str:
    """
    Redact detected PII from the text, e.g. "email John@x.com"
    -> "email <EMAIL_ADDRESS>".
    """
    if not text.strip():
        return text

    analyzer = get_analyzer()
    anonymizer = get_anonymizer()

    results = analyzer.analyze(text=text, language="en")

    if not results:
        return text

    return anonymizer.anonymize(text=text, analyzer_results=results).text
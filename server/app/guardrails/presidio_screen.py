"""

PII detection and anonymization using Microsoft Presidio.

"""

from functools import lru_cache

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from app.logging import logfire

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

    PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
]
    if not text.strip():
        return False

    analyzer = get_analyzer()

    results = analyzer.analyze(
        text=text,
        language="en",
        entities=PII_ENTITIES,
    )
    logfire.info("Presidio PII detection results", results=results)

    return bool(results)


def anonymize_pii(text: str) -> tuple[str, bool]:
    if not text.strip():
        return text, False

    analyzer = get_analyzer()
    anonymizer = get_anonymizer()

    results = analyzer.analyze(
        text=text,
        language="en",
    )

    

    if not results:
        return text, False

    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
    )

    return anonymized.text, True
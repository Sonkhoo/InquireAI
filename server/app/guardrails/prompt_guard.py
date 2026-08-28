from app.logging import logfire
from functools import lru_cache
from typing import Any
from app.config import get_settings

settings = get_settings()

PROMPT_GUARD_MODEL = settings.prompt_guard_model
MALICIOUS_THRESHOLD = 0.5


@lru_cache(maxsize=1)
def get_prompt_guard() -> Any:
    """
    Lazily load the Prompt Guard model once per process.

    lru_cache caches the model object, not query results.
    transformers is imported here so importing this module stays cheap.
    """
    from transformers import pipeline

    return pipeline(
        "text-classification",
        model=PROMPT_GUARD_MODEL,
    )


def detect_prompt_injection(
    text: str,
    threshold: float = MALICIOUS_THRESHOLD,
) -> bool:
    """
    Detect whether the input appears to contain a prompt injection
    or jailbreak attempt.

    Returns:
        True  -> malicious / prompt injection detected
        False -> benign
    """

    if not text.strip():
        return False

    result = get_prompt_guard()(text, truncation=True)[0]

    label = str(result["label"]).upper()
    score = float(result["score"])

    # Prompt Guard returns LABEL_1 for malicious content.
    malicious = label == "LABEL_1" and score >= threshold

    if malicious:
        logfire.warning(
            "Prompt injection detected",
            score=score,
        )
    else:
        logfire.info(
            "Prompt guard allowed query",
            label=label,
            score=score,
        )

    return malicious
class RetryableParseError(Exception):
    """Transient failure (I/O, timeout) — safe to retry."""
    pass


class TerminalParseError(Exception):
    """Non-retryable failure (corrupt file, unsupported content) — do not retry."""
    pass

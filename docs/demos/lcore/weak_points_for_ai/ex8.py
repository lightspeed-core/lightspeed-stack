# True constants are possible in Python

# Max seconds to wait for topic summary in background task after interrupt persist.
TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS: Final[float] = 30.0

# Supported attachment types
ATTACHMENT_TYPES: Final[frozenset] = frozenset(
    {
        "alert",
        "api object",
        "configuration",
        "error message",
        "event",
        "log",
        "stack trace",
    }
)

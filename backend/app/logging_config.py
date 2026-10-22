import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure single-line log output. Log records must not contain message text."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

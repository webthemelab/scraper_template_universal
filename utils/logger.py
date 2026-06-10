# utils/logger.py
# ─────────────────────────────────────────────────────────────
# Centralised logging using loguru.
# Features:
#   • Coloured terminal output
#   • Rotating file logs (daily, kept 30 days)
#   • Automatic masking of passwords/keys in log messages
#   • Structured context (domain, worker_id, proxy) on each record
# ─────────────────────────────────────────────────────────────

import re
import sys
from loguru import logger
from config.settings import settings

# Patterns that should never appear in log files
_SENSITIVE_PATTERNS = [
    (re.compile(r"(password[=: ]+)\S+",      re.I), r"\1***"),
    (re.compile(r"(PGPASSWORD[=: ]+)\S+",    re.I), r"\1***"),
    (re.compile(r"(proxy[_-]?pass[=: ]+)\S+",re.I), r"\1***"),
    (re.compile(r"(api[_-]?key[=: ]+)\S+",   re.I), r"\1***"),
    (re.compile(r"(token[=: ]+)\S+",          re.I), r"\1***"),
    # Mask passwords embedded in proxy URLs:  http://user:PASS@host
    (re.compile(r"(https?://[^:]+:)[^@]+(@)", re.I), r"\1***\2"),
]


def _mask(message: str) -> str:
    """Remove sensitive values from a log message."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class _MaskingFilter:
    """loguru sink wrapper that applies secret masking before writing."""
    def __init__(self, sink):
        self._sink = sink

    def write(self, message):
        self._sink.write(_mask(str(message)))

    def flush(self):
        if hasattr(self._sink, "flush"):
            self._sink.flush()


# ── Build logger ─────────────────────────────────────────────
logger.remove()   # drop the default handler

_fmt_console = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[domain]}</cyan> | "
    "{message}"
)
_fmt_file = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
    "{extra[domain]} | worker={extra[worker_id]} | {message}"
)

if settings.logging.mask_secrets:
    logger.add(
        _MaskingFilter(sys.stdout),
        level=settings.logging.level,
        format=_fmt_console,
        colorize=True,
    )
else:
    logger.add(sys.stdout, level=settings.logging.level, format=_fmt_console, colorize=True)

logger.add(
    f"{settings.logging.dir}/scraper.log",
    level="DEBUG",
    format=_fmt_file,
    rotation=settings.logging.rotation,
    retention=settings.logging.retention,
    encoding="utf-8",
    filter=lambda r: _mask(r["message"]) or True,  # mask file logs too
)

# Bind default context values so every log record has these keys
logger = logger.bind(domain="system", worker_id=0)


def get_logger(domain: str = "system", worker_id: int = 0):
    """Return a logger pre-bound with domain and worker context."""
    return logger.bind(domain=domain, worker_id=worker_id)

import re
import time
import threading
from collections import OrderedDict
from typing import Dict, List

# Thread-safe, bounded in-memory store for live terminal logs & active background tasks
_lock = threading.Lock()
_MAX_TICKERS = 100
_MAX_LOGS_PER_TICKER = 150
_VECTORIZATION_TIMEOUT_SEC = 900  # 15 minutes max before a lock is considered stale

logs: "OrderedDict[str, List[str]]" = OrderedDict()
_active_vectorizations: Dict[str, float] = {}

# Regex to redact accidental API keys or tokens in exception strings before public logging
_SECRET_PATTERNS = re.compile(
    r"((?:apikey|api_key|apiKey|token|key|secret)=)[^&\s'\"]+",
    re.IGNORECASE,
)


def sanitize_log_message(message: str) -> str:
    """Redacts any query-string API keys or tokens from log/error messages."""
    if not isinstance(message, str):
        message = str(message)
    return _SECRET_PATTERNS.sub(r"\1[REDACTED]", message)


def log_update(ticker: str, message: str):
    """Pushes a new sanitized log message to the ticker's bounded status queue."""
    ticker_key = ticker.strip().upper()
    clean_msg = sanitize_log_message(message)

    with _lock:
        if ticker_key in logs:
            logs.move_to_end(ticker_key)
        else:
            if len(logs) >= _MAX_TICKERS:
                logs.popitem(last=False)  # Evict oldest ticker log buffer
            logs[ticker_key] = []

        ticker_logs = logs[ticker_key]
        ticker_logs.append(clean_msg)
        if len(ticker_logs) > _MAX_LOGS_PER_TICKER:
            del ticker_logs[: len(ticker_logs) - _MAX_LOGS_PER_TICKER]

    print(f"[{ticker_key}] {clean_msg}")


def get_logs(ticker: str) -> List[str]:
    """Retrieves a snapshot of all current logs for a ticker."""
    ticker_key = ticker.strip().upper()
    with _lock:
        return list(logs.get(ticker_key, []))


def clear_logs(ticker: str):
    """
    Wipes the slate clean for a fresh request, unless a background vectorization
    job is actively running for this ticker (in which case we keep context).
    """
    ticker_key = ticker.strip().upper()
    with _lock:
        if is_vectorizing_unlocked(ticker_key):
            # Preserve active background vectorization logs so the user doesn't lose visibility
            return
        if ticker_key in logs:
            logs[ticker_key] = []


def is_vectorizing_unlocked(ticker_key: str) -> bool:
    """Internal helper (requires _lock held) to check if ticker is actively vectorizing."""
    started_at = _active_vectorizations.get(ticker_key)
    if started_at is None:
        return False
    if (time.time() - started_at) > _VECTORIZATION_TIMEOUT_SEC:
        del _active_vectorizations[ticker_key]
        return False
    return True


def is_vectorizing(ticker: str) -> bool:
    """Returns True if a background SEC vectorization job is currently active for ticker."""
    ticker_key = ticker.strip().upper()
    with _lock:
        return is_vectorizing_unlocked(ticker_key)


def try_acquire_vectorization(ticker: str) -> bool:
    """
    Atomically marks a ticker as undergoing background SEC vectorization.
    Returns True if acquired, False if another worker is already vectorizing it.
    """
    ticker_key = ticker.strip().upper()
    with _lock:
        if is_vectorizing_unlocked(ticker_key):
            return False
        _active_vectorizations[ticker_key] = time.time()
        return True


def release_vectorization(ticker: str):
    """Releases the background vectorization lock for a ticker."""
    ticker_key = ticker.strip().upper()
    with _lock:
        _active_vectorizations.pop(ticker_key, None)
from typing import Dict, List

# In-memory store for live terminal logs
logs: Dict[str, List[str]] = {}

def log_update(ticker: str, message: str):
    """Pushes a new log message to the ticker's status queue."""
    ticker = ticker.upper()
    if ticker not in logs:
        logs[ticker] = []
    logs[ticker].append(message)
    print(f"[{ticker}] {message}") # Also print to your standard VS Code terminal

def get_logs(ticker: str) -> List[str]:
    """Retrieves all current logs for a ticker."""
    return logs.get(ticker.upper(), [])

def clear_logs(ticker: str):
    """Wipes the slate clean for a fresh request."""
    if ticker.upper() in logs:
        logs[ticker.upper()] = []
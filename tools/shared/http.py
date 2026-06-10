"""Rate-limited HTTP GET wrapper for LinkedIn public endpoints."""
from __future__ import annotations
import os, time
from dataclasses import dataclass
import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_THROTTLE_S = 1.5

@dataclass
class _State:
    last_call: float = 0.0
    throttle_s: float = DEFAULT_THROTTLE_S

_state = _State()

def set_throttle(seconds: float) -> None:
    _state.throttle_s = seconds

def get(url: str, *, accept: str = "text/html,*/*;q=0.8") -> requests.Response:
    elapsed = time.monotonic() - _state.last_call
    if elapsed < _state.throttle_s:
        time.sleep(_state.throttle_s - elapsed)
    headers = {
        "User-Agent": os.environ.get("LINKEDIN_USER_AGENT", DEFAULT_UA),
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    _state.last_call = time.monotonic()
    return resp

"""
Shared rate limiting and HTTP session for all TFRRS scraping.
Enforces minimum delays between requests and exponential backoff on errors.
"""
import time
import random
import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_last_request_time: float = 0.0


def _throttle(min_delay: float, max_delay: float) -> None:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    delay = random.uniform(min_delay, max_delay)
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _last_request_time = time.monotonic()


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    # Only retry on network errors (not HTTP errors — we handle those ourselves)
    retry = Retry(total=0)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = build_session()
    return _session


def fetch(
    url: str,
    min_delay: float = 1.5,
    max_delay: float = 3.0,
    backoff_base: float = 2.0,
    max_retries: int = 4,
    params: Optional[dict] = None,
) -> requests.Response:
    """
    Fetch a URL with rate limiting and exponential backoff on 429/503.
    Raises requests.HTTPError for unrecoverable HTTP errors.
    """
    session = get_session()
    attempt = 0
    while True:
        _throttle(min_delay, max_delay)
        try:
            resp = session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            logger.warning("Network error fetching %s: %s", url, exc)
            if attempt >= max_retries:
                raise
            wait = backoff_base ** attempt
            logger.info("Retrying in %.1fs (attempt %d/%d)", wait, attempt + 1, max_retries)
            time.sleep(wait)
            attempt += 1
            continue

        if resp.status_code in (429, 503):
            if attempt >= max_retries:
                resp.raise_for_status()
            wait = backoff_base ** attempt
            logger.warning("Rate limited (%d) on %s — waiting %.1fs", resp.status_code, url, wait)
            time.sleep(wait)
            attempt += 1
            continue

        resp.raise_for_status()
        logger.debug("GET %s → %d (%d bytes)", url, resp.status_code, len(resp.content))
        return resp

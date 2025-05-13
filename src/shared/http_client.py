import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import time
import logging
import traceback

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(handler)


def make_session() -> requests.Session:
    """Create a Session with a urllib3 Retry on POST + Connection: close."""
    s = requests.Session()

    retry_cfg = Retry(
        total=5,                    # 1 attempt + 5 retries
        backoff_factor=1,           # delays: 1s, 2s, 4s, 8s, 16s
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],   # only retry POST
        raise_on_status=False,      # let us handle HTTPError manually
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry_cfg)
    s.mount("https://", adapter)

    # avoid stale TLS sockets
    s.headers.update({"Connection": "close"})
    return s


# one shared session for your entire process
_session = make_session()


def safe_post(
    url: str,
    payload: dict,
    timeout: tuple[int, int] = (5, 15),
    max_json_retries: int = 2,
    reset_session_on_error: bool = True
) -> dict | None:
    """
    POST with urllib3-retries + JSON-retries + optional session reset.

    Returns parsed JSON on success, or None on total failure.
    """
    global _session

    for attempt in range(max_json_retries + 1):
        try:
            resp = _session.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()      # raises on HTTP 4xx/5xx
            return resp.json()           # may raise JSONDecodeError

        except json.JSONDecodeError as jde:
            log.warning("Invalid JSON on attempt %d/%d: %s",
                        attempt + 1, max_json_retries + 1, jde)
            traceback.print_exc()

        except requests.RequestException as re:
            # this includes timeouts, connection errors, HTTPError after retries
            log.error("RequestException on attempt %d: %s",
                      attempt + 1, re)
            traceback.print_exc()
            if reset_session_on_error:
                log.info("Reinitializing HTTP session (stale socket?)")
                try:
                    _session.close()
                except Exception:
                    pass
                _session = make_session()

        # exponential backoff between JSON retries
        if attempt < max_json_retries:
            sleep_sec = 2 ** attempt
            log.info("Sleeping %ds before next JSON retry...", sleep_sec)
            time.sleep(sleep_sec)

    # all attempts failed
    log.error("safe_post: gave up after %d JSON attempts", max_json_retries + 1)
    return None

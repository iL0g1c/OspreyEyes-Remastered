import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError, RequestException
from urllib3.util.retry import Retry
import json
import time
import logging
import traceback
import ssl
import os

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
log.addHandler(handler)

CERT_PATH = "pinned-server-cert.pem"


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

def fetch_and_store_cert(hostname, port=443, path=CERT_PATH):
    """
    Retrieves the server's current leaf certificate and writes it to `path`.
    """
    cert_pem = ssl.get_server_certificate((hostname, port))
    with open(path, "w") as f:
        f.write(cert_pem)
    return path

def safe_post(
    url: str,
    payload: dict,
    timeout: tuple[int, int] = (5, 15),
    max_json_retries: int = 2,
    reset_session_on_error: bool = True,
    **request_kwargs,            #  <-- forward anything else (cookies, headers…)
) -> dict | None:
    """
    POST a JSON payload with robust retries.

    • First layer of retries comes from urllib3.Retry inside _session
    • Second layer retries JSON-parse errors or exhausted network failures
    • Optionally rebuilds the Session if we suspect a stale socket
    • Returns parsed JSON on success, or None on total failure
    """
    global _session

    hostname = requests.utils.urlparse(url).hostname
    # ensure we have an initial cert on disk
    if not request_kwargs.get("verify") and not os.path.exists(CERT_PATH):
        fetch_and_store_cert(hostname)

    # always start by verifying against our pinned cert
    request_kwargs["verify"] = CERT_PATH

    for attempt in range(max_json_retries + 1):
        try:
            resp = _session.post(
                url,
                json=payload,
                timeout=timeout,
                **request_kwargs
            )   
            if resp.text != "":
                resp.raise_for_status()
                return resp.json()
            else:
                log.error(f"resp: {str(type(resp))}")
                log.error(f"resp.text: {str(type(resp.text))}")
                log.error("Response is None, no JSON to parse")
                return None

        # ---------- retry on bad JSON -----------------------------------------
        except json.JSONDecodeError as jde:
            log.error("Failed to parse JSON from %s (status %d): %s",
              url, resp.status_code, jde)
            
            log.error("Response text repr: %r", resp.text)
            traceback.print_exc()

        # ---------- retry on SSL errors ---------------------------------------
        except SSLError as ssl_err:
            fetch_and_store_cert(hostname)
            continue
        
        # ---------- retry on network / HTTP errors ----------------------------
        except requests.RequestException as re:
            log.error("RequestException on attempt %d: %s", attempt + 1, re)
            traceback.print_exc()

            if reset_session_on_error:
                log.info("Re-initialising HTTP session (possible stale socket)")
                try:
                    _session.close()
                except Exception:
                    pass
                _session = make_session()

        # ---------- back-off before the next loop iteration -------------------
        if attempt < max_json_retries:
            sleep_sec = 2 ** attempt            # 1 s, 2 s, 4 s …
            log.info("Sleeping %ds before retry", sleep_sec)
            time.sleep(sleep_sec)

    # All retries failed
    log.error("safe_post: gave up after %d attempts", max_json_retries + 1)
    return None

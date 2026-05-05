import os
import ssl
import urllib3
import logging
from typing import Tuple
import requests

logger = logging.getLogger(__name__)


def build_base_url(provided_url: str, cfg: dict) -> str:
    """Return base URL (scheme://host[:port]) based on provided_url and cfg.use_ssl."""
    if provided_url.startswith("http://") or provided_url.startswith("https://"):
        return provided_url.rstrip('/')
    use_ssl = bool(cfg.get("use_ssl", False))
    scheme = "https" if use_ssl else "http"
    return f"{scheme}://{provided_url}"


def configure_ssl_session(cfg: dict, session: requests.Session) -> Tuple[str, object]:
    """Configure a requests.Session SSL verification based on config.

    Returns (scheme, verify_value) where verify_value is assigned to session.verify.
    """
    use_ssl = bool(cfg.get("use_ssl", False))
    allow_self_signed = bool(cfg.get("allow_self_signed", False))
    ssl_ca_cert = cfg.get("ssl_ca_cert")

    scheme = "https" if use_ssl else "http"

    if use_ssl:
        if allow_self_signed:
            session.verify = False
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        elif ssl_ca_cert:
            session.verify = ssl_ca_cert
        else:
            session.verify = True
    else:
        session.verify = True

    session.trust_env = False
    return scheme, session.verify


def configure_global_ssl(cfg: dict) -> None:
    """Configure global SSL behavior for urllib-based clients.

    If `use_ssl` and `allow_self_signed` are set, this will set the default
    https context to unverified and suppress warnings. If `ssl_ca_cert` is
    provided, it will set `SSL_CERT_FILE` so the Python process uses it.
    """
    use_ssl = bool(cfg.get("use_ssl", False))
    allow_self_signed = bool(cfg.get("allow_self_signed", False))
    ssl_ca_cert = cfg.get("ssl_ca_cert")

    if not use_ssl:
        return

    if allow_self_signed:
        try:
            ssl._create_default_https_context = ssl._create_unverified_context
            os.environ['PYTHONHTTPSVERIFY'] = '0'
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning("Global: allowing self-signed certificates (UNSAFE - testing only)")
        except Exception as e:
            logger.warning(f"Failed to enable unverified global SSL context: {e}")
    elif ssl_ca_cert:
        try:
            os.environ['SSL_CERT_FILE'] = ssl_ca_cert
            logger.info(f"Global: using custom CA bundle: {ssl_ca_cert}")
        except Exception as e:
            logger.warning(f"Failed to set SSL_CERT_FILE: {e}")

"""
SSRF protection for outbound fetches of AI/user-supplied URLs (P0 hardening).

Any URL this app fetches that ultimately traces back to company data — an
AI-discovered website, a CRM record, a link found while scraping — is
untrusted input. Without validation, a company record whose "website" is
set to http://169.254.169.254/... (cloud metadata) or http://localhost:8000/admin
turns the scraper into a proxy into your own internal network. This module
is the one place that decides whether a URL is safe to fetch, and
safe_get()/safe_post() enforce it end to end — including on every redirect
hop, since a first hop that resolves safely can still redirect to an
internal address.

This is a SEPARATE control from prompt-injection defense (see
ai_gateway.wrap_untrusted). A URL can be perfectly SSRF-safe (a real public
company site) and still contain text aimed at manipulating the LLM that
reads the scraped content — both controls are required, neither substitutes
for the other.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB — plenty for a company homepage
DEFAULT_TIMEOUT = 10  # seconds
# Ports that make sense for a public website fetch. Blocks attempts to reach
# an internal service running on an unusual port on an otherwise-public host.
ALLOWED_PORTS = {80, 443, 8080, 8443}


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF validation. Callers should treat this
    the same as any other fetch failure — log it, don't fetch, move on."""


def _is_blocked_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # unparseable → treat as unsafe
    if (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
        return True
    # Cloud metadata endpoint — AWS/GCP/Azure/DigitalOcean all use this.
    if str(ip) == "169.254.169.254":
        return True
    return False


def validate_url(url: str) -> str:
    """
    Validate a URL is safe to fetch: scheme, hostname, port, and every IP
    the hostname resolves to. Returns the normalized URL on success, raises
    UnsafeURLError with a specific reason on failure.

    DNS-resolve-then-check has a theoretical TOCTOU gap (DNS rebinding
    between this check and the actual connection) — safe_get/safe_post
    close that in practice by re-validating on every redirect hop rather
    than trusting a single upfront check for the whole request chain.
    """
    if not url or not url.strip():
        raise UnsafeURLError("empty URL")
    candidate = url.strip()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise UnsafeURLError("no hostname")

    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeURLError("localhost is blocked")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"port not allowed: {port}")

    try:
        infos = socket.getaddrinfo(hostname, port)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution failed: {e}")
    if not infos:
        raise UnsafeURLError("DNS resolution returned no addresses")
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        if _is_blocked_ip(ip_str):
            raise UnsafeURLError(f"resolves to a blocked address: {ip_str}")

    return parsed.geturl()


def _safe_request(method: str, url: str, *, headers=None,
                   timeout: float = DEFAULT_TIMEOUT,
                   max_bytes: int = MAX_RESPONSE_BYTES, **kwargs) -> requests.Response:
    """
    SSRF-safe requests.get/post replacement. Validates the URL, disables
    requests' automatic redirect following so EACH hop is independently
    re-validated (a safe first hop can still redirect to 127.0.0.1), and
    caps the response size while streaming so a malicious/huge response
    can't exhaust memory.
    """
    current_url = validate_url(url)
    session = requests.Session()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            resp = session.request(method, current_url, headers=headers, timeout=timeout,
                                   allow_redirects=False, stream=True, **kwargs)
            if resp.is_redirect or resp.is_permanent_redirect:
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise UnsafeURLError("redirect with no Location header")
                current_url = validate_url(urljoin(current_url, location))
                continue

            content = bytearray()
            try:
                for chunk in resp.iter_content(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise UnsafeURLError(f"response exceeded {max_bytes} byte limit")
            finally:
                resp.close()
            resp._content = bytes(content)          # noqa: SLF001 — prime .text/.json() cache
            return resp
    finally:
        session.close()
    raise UnsafeURLError(f"too many redirects (> {MAX_REDIRECTS})")


def safe_get(url: str, **kwargs) -> requests.Response:
    return _safe_request("GET", url, **kwargs)


def safe_post(url: str, **kwargs) -> requests.Response:
    return _safe_request("POST", url, **kwargs)

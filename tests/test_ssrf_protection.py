"""
SSRF protection tests (P0 hardening).

app/utils/url_safety.py is the one place that decides whether a URL derived
from company data (AI-discovered website, CRM record, scraped link) is safe
to fetch. These tests cover the blocked/allowed matrix without making real
network calls for the blocked cases (DNS resolution for literal IPs doesn't
hit the network) and mock DNS + the HTTP layer for the redirect-safety test
so it's deterministic and doesn't depend on binding a real socket.
"""
import socket
import unittest
from unittest.mock import MagicMock, patch

import requests

from app.utils import url_safety
from app.utils.url_safety import validate_url, safe_get, UnsafeURLError, ALLOWED_PORTS


class URLValidationTests(unittest.TestCase):

    def test_01_blocks_cloud_metadata_endpoint(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_02_blocks_loopback(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://127.0.0.1/")
        with self.assertRaises(UnsafeURLError):
            validate_url("http://localhost/")

    def test_03_blocks_private_ranges(self):
        for host in ("http://10.0.0.5/", "http://172.16.0.1/", "http://192.168.1.1/"):
            with self.assertRaises(UnsafeURLError):
                validate_url(host)

    def test_04_blocks_disallowed_scheme(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("ftp://example.com/")
        with self.assertRaises(UnsafeURLError):
            validate_url("file:///etc/passwd")

    def test_05_blocks_unusual_port(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("http://example.com:9999/")
        # sanity: the allowed set itself covers the common web ports
        self.assertEqual(ALLOWED_PORTS, {80, 443, 8080, 8443})

    def test_06_blocks_empty_url(self):
        with self.assertRaises(UnsafeURLError):
            validate_url("")

    def test_07_allows_bare_hostname_defaults_to_https(self):
        normalized = validate_url("example.com")
        self.assertTrue(normalized.startswith("https://"))

    def test_08_allows_explicit_public_https_url(self):
        normalized = validate_url("https://example.com/about")
        self.assertEqual(normalized, "https://example.com/about")


class SafeGetRedirectTests(unittest.TestCase):
    """
    The real attack this guards against: a URL that passes the initial
    safety check (resolves to a public IP) but whose HTTP response then
    redirects to an internal/metadata address. If safe_get only validated
    the first hop, this would sail right through. DNS and the HTTP layer
    are mocked so the test is deterministic and makes no real network calls.
    """

    def test_09_redirect_to_metadata_endpoint_is_rejected(self):
        def fake_getaddrinfo(host, port, *a, **kw):
            if host == "safe-looking.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
            # getaddrinfo on a literal IP just echoes it back (matches real behavior) —
            # this is what the redirect target's own validate_url call will do.
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port))]

        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.is_permanent_redirect = False
        redirect_response.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        redirect_response.close = MagicMock()

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo), \
             patch.object(requests.Session, "request", return_value=redirect_response):
            with self.assertRaises(UnsafeURLError) as ctx:
                safe_get("http://safe-looking.example/")
            self.assertIn("blocked address", str(ctx.exception))

    def test_10_normal_response_is_not_treated_as_redirect(self):
        def fake_getaddrinfo(host, port, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        ok_response = MagicMock()
        ok_response.is_redirect = False
        ok_response.is_permanent_redirect = False
        ok_response.iter_content.return_value = [b"hello world"]
        ok_response.close = MagicMock()

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo), \
             patch.object(requests.Session, "request", return_value=ok_response):
            resp = safe_get("http://safe-looking.example/")
            self.assertEqual(resp._content, b"hello world")

    def test_11_oversized_response_is_rejected(self):
        def fake_getaddrinfo(host, port, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        huge_response = MagicMock()
        huge_response.is_redirect = False
        huge_response.is_permanent_redirect = False
        huge_response.iter_content.return_value = [b"x" * 1024] * 100
        huge_response.close = MagicMock()

        with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo), \
             patch.object(requests.Session, "request", return_value=huge_response):
            with self.assertRaises(UnsafeURLError):
                safe_get("http://safe-looking.example/", max_bytes=1024)


if __name__ == "__main__":
    unittest.main()

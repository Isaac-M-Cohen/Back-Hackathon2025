"""Tests for WebExecutor URL validation (Issue 1 - Command Injection Prevention)."""

import pytest

from command_controller.web_executor import WebExecutor


class TestWebExecutorURLValidation:
    """Test suite for _is_safe_url() security validation."""

    def test_safe_url_https(self):
        """Test that https URLs are safe."""
        assert WebExecutor._is_safe_url("https://example.com") is True
        assert WebExecutor._is_safe_url("https://www.google.com/search?q=test") is True

    def test_safe_url_http(self):
        """Test that http URLs are safe."""
        assert WebExecutor._is_safe_url("http://example.com") is True
        assert WebExecutor._is_safe_url("http://example.com/path?query=1") is True

    def test_unsafe_url_none(self):
        """Test that None is rejected."""
        assert WebExecutor._is_safe_url(None) is False

    def test_unsafe_url_empty(self):
        """Test that empty string is rejected."""
        assert WebExecutor._is_safe_url("") is False

    def test_unsafe_url_file_scheme(self):
        """Test that file:// scheme is rejected."""
        assert WebExecutor._is_safe_url("file:///etc/passwd") is False

    def test_unsafe_url_javascript_scheme(self):
        """Test that javascript: scheme is rejected."""
        assert WebExecutor._is_safe_url("javascript:alert(1)") is False

    def test_unsafe_url_data_scheme(self):
        """Test that data: scheme is rejected."""
        assert WebExecutor._is_safe_url("data:text/html,<script>alert(1)</script>") is False

    def test_unsafe_url_localhost(self):
        """Test that localhost is rejected (SSRF protection)."""
        assert WebExecutor._is_safe_url("http://localhost/") is False
        assert WebExecutor._is_safe_url("https://localhost:8080/api") is False

    def test_unsafe_url_127_0_0_1(self):
        """Test that 127.0.0.1 is rejected (SSRF protection)."""
        assert WebExecutor._is_safe_url("http://127.0.0.1/") is False
        assert WebExecutor._is_safe_url("https://127.0.0.1:3000/") is False

    def test_unsafe_url_ipv6_loopback(self):
        """Test that IPv6 loopback is rejected."""
        assert WebExecutor._is_safe_url("http://[::1]/") is False

    def test_unsafe_url_private_ip_192(self):
        """Test that 192.168.x.x private IPs are rejected."""
        assert WebExecutor._is_safe_url("http://192.168.1.1/") is False
        assert WebExecutor._is_safe_url("http://192.168.0.1/router") is False

    def test_unsafe_url_private_ip_10(self):
        """Test that 10.x.x.x private IPs are rejected."""
        assert WebExecutor._is_safe_url("http://10.0.0.1/") is False
        assert WebExecutor._is_safe_url("http://10.255.255.255/") is False

    def test_unsafe_url_private_ip_172(self):
        """Test that 172.16-31.x.x private IPs are rejected."""
        assert WebExecutor._is_safe_url("http://172.16.0.1/") is False
        assert WebExecutor._is_safe_url("http://172.31.255.255/") is False

    def test_unsafe_url_metadata_service(self):
        """Test that cloud metadata service IP is rejected."""
        assert WebExecutor._is_safe_url("http://169.254.169.254/") is False
        assert WebExecutor._is_safe_url("http://169.254.169.254/latest/meta-data") is False

    def test_unsafe_url_too_long(self):
        """Test that overly long URLs are rejected (DoS protection)."""
        long_url = "https://example.com/" + "a" * 3000
        assert WebExecutor._is_safe_url(long_url) is False

    def test_safe_url_at_max_length(self):
        """Test that URLs at max length are accepted."""
        max_url = "https://example.com/" + "a" * 2020  # Just under 2048
        assert WebExecutor._is_safe_url(max_url) is True

    def test_unsafe_url_no_hostname(self):
        """Test that URLs without hostname are rejected."""
        assert WebExecutor._is_safe_url("http:///path") is False

    def test_safe_url_public_ip(self):
        """Test that public IPs are allowed."""
        assert WebExecutor._is_safe_url("http://8.8.8.8/") is True
        assert WebExecutor._is_safe_url("https://1.1.1.1/") is True

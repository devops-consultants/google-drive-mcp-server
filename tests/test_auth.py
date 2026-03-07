"""Tests for Bearer token authentication."""

import pytest
from google_drive_mcp_server.server import _extract_bearer_token


def test_extract_bearer_token_valid():
    """Valid Bearer token is extracted."""
    assert _extract_bearer_token("Bearer abc123") == "abc123"


def test_extract_bearer_token_case_insensitive():
    """Bearer prefix is case-insensitive."""
    assert _extract_bearer_token("bearer abc123") == "abc123"
    assert _extract_bearer_token("BEARER abc123") == "abc123"


def test_extract_bearer_token_none():
    """None authorization returns None."""
    assert _extract_bearer_token(None) is None


def test_extract_bearer_token_empty():
    """Empty authorization returns None."""
    assert _extract_bearer_token("") is None


def test_extract_bearer_token_no_bearer_prefix():
    """Non-Bearer auth returns None."""
    assert _extract_bearer_token("Basic abc123") is None


def test_extract_bearer_token_only_bearer():
    """Just 'Bearer' with no token returns None."""
    assert _extract_bearer_token("Bearer ") is None
    assert _extract_bearer_token("Bearer") is None

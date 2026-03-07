"""Tests for the Google Drive API client."""

import pytest
import httpx
import respx

from google_drive_mcp_server.drive_client import (
    DriveClient,
    DriveAPIError,
    PathCache,
    _map_error,
    is_text_mime,
    DRIVE_API_BASE,
    DRIVE_UPLOAD_BASE,
    DEFAULT_MAX_FILE_SIZE,
    FOLDER_MIME_TYPE,
)


# --- Unit tests for helper functions ---


class TestIsTextMime:
    def test_text_plain(self):
        assert is_text_mime("text/plain") is True

    def test_text_html(self):
        assert is_text_mime("text/html") is True

    def test_application_json(self):
        assert is_text_mime("application/json") is True

    def test_application_xml(self):
        assert is_text_mime("application/xml") is True

    def test_application_yaml(self):
        assert is_text_mime("application/yaml") is True

    def test_application_octet_stream(self):
        assert is_text_mime("application/octet-stream") is False

    def test_image_png(self):
        assert is_text_mime("image/png") is False

    def test_none_type(self):
        assert is_text_mime(None) is False

    def test_text_with_charset(self):
        assert is_text_mime("text/plain; charset=utf-8") is True


class TestPathCache:
    def test_set_and_get(self):
        cache = PathCache()
        cache.set("/Documents", "folder-id-1")
        assert cache.get("/Documents") == "folder-id-1"

    def test_case_insensitive(self):
        cache = PathCache()
        cache.set("/Documents", "folder-id-1")
        assert cache.get("/documents") == "folder-id-1"
        assert cache.get("/DOCUMENTS") == "folder-id-1"

    def test_get_missing(self):
        cache = PathCache()
        assert cache.get("/nonexistent") is None

    def test_invalidate(self):
        cache = PathCache()
        cache.set("/Documents", "folder-id-1")
        cache.invalidate("/Documents")
        assert cache.get("/Documents") is None

    def test_clear(self):
        cache = PathCache()
        cache.set("/a", "1")
        cache.set("/b", "2")
        cache.clear()
        assert cache.get("/a") is None
        assert cache.get("/b") is None

    def test_trailing_slash_normalised(self):
        cache = PathCache()
        cache.set("/Documents/", "folder-id-1")
        assert cache.get("/Documents") == "folder-id-1"


class TestMapError:
    def test_401_maps_to_auth_expired(self):
        response = httpx.Response(401, json={"error": {"message": "Token expired"}})
        err = _map_error(response)
        assert err.error == "auth_expired"

    def test_403_maps_to_permission_denied(self):
        response = httpx.Response(403, json={"error": {"message": "Access denied"}})
        err = _map_error(response)
        assert err.error == "permission_denied"

    def test_404_maps_to_not_found(self):
        response = httpx.Response(404, json={"error": {"message": "Not found"}})
        err = _map_error(response)
        assert err.error == "not_found"

    def test_412_maps_to_conflict(self):
        response = httpx.Response(412, json={"error": {"message": "Precondition failed"}})
        err = _map_error(response)
        assert err.error == "conflict"

    def test_429_maps_to_rate_limited(self):
        response = httpx.Response(429, headers={"Retry-After": "5"}, json={"error": {"message": "Throttled"}})
        err = _map_error(response)
        assert err.error == "rate_limited"
        assert "5" in err.message

    def test_500_maps_to_api_error(self):
        response = httpx.Response(500, json={"error": {"message": "Internal error"}})
        err = _map_error(response)
        assert err.error == "api_error"

    def test_context_included_in_message(self):
        response = httpx.Response(404, json={"error": {"message": "Not found"}})
        err = _map_error(response, "list_files(/test)")
        assert "list_files(/test)" in err.message


class TestDriveAPIError:
    def test_to_dict_basic(self):
        err = DriveAPIError("not_found", "File not found")
        assert err.to_dict() == {"error": "not_found", "message": "File not found"}

    def test_to_dict_with_etag(self):
        err = DriveAPIError("conflict", "ETag mismatch", etag="abc123")
        d = err.to_dict()
        assert d["error"] == "conflict"
        assert d["etag"] == "abc123"


# --- Path resolution tests ---

@pytest.mark.asyncio
class TestPathResolution:
    @respx.mock
    async def test_resolve_root(self):
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/")
            assert result == "root"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_empty(self):
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("")
            assert result == "root"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_my_drive_root(self):
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/My Drive")
            assert result == "root"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_single_folder(self):
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [{"id": "folder-1", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/Documents")
            assert result == "folder-1"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_nested_path(self):
        # First call resolves "Documents"
        # Second call resolves "Reports" inside Documents
        call_count = 0
        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={
                    "files": [{"id": "folder-1", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
                })
            else:
                return httpx.Response(200, json={
                    "files": [{"id": "folder-2", "name": "Reports", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
                })

        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/Documents/Reports")
            assert result == "folder-2"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_not_found(self):
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client._resolve_path("/nonexistent")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_shared_drive(self):
        # First mock: list shared drives
        respx.get(f"{DRIVE_API_BASE}/drives").mock(
            return_value=httpx.Response(200, json={
                "drives": [{"id": "drive-1", "name": "TeamDrive"}]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/Shared drives/TeamDrive")
            assert result == "drive-1"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_shared_drive_not_found(self):
        respx.get(f"{DRIVE_API_BASE}/drives").mock(
            return_value=httpx.Response(200, json={"drives": []})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client._resolve_path("/Shared drives/NonExistent")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_uses_cache(self):
        """Second resolve should use cache, not make API calls."""
        route = respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [{"id": "folder-1", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
            })
        )
        cache = PathCache()
        client = DriveClient(token="test-token", path_cache=cache)
        try:
            await client._resolve_path("/Documents")
            # Second call should use cache
            result = await client._resolve_path("/Documents")
            assert result == "folder-1"
            assert route.call_count == 1  # Only one API call
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_case_insensitive(self):
        """Path resolution is case-insensitive."""
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [{"id": "folder-1", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/documents")
            assert result == "folder-1"
        finally:
            await client.close()

    @respx.mock
    async def test_resolve_duplicate_returns_most_recent(self):
        """When duplicate names exist, return most recently modified."""
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [
                    {"id": "newer", "name": "report.md", "modifiedTime": "2024-06-01T00:00:00Z", "mimeType": "text/markdown"},
                    {"id": "older", "name": "report.md", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": "text/markdown"},
                ]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client._resolve_path("/report.md")
            # Should return the first match (sorted by modifiedTime desc)
            assert result == "newer"
        finally:
            await client.close()

    @respx.mock
    async def test_shared_drives_requires_drive_name(self):
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client._resolve_path("/Shared drives")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()

    @respx.mock
    async def test_cache_no_collision_between_drives(self):
        """Cache keys include drive prefix so My Drive and Shared drives don't collide."""
        call_count = [0]
        def side_effect(request):
            call_count[0] += 1
            url_str = str(request.url)
            # Shared drive listing
            if "drives" in url_str and "files" not in url_str:
                return httpx.Response(200, json={
                    "drives": [{"id": "drive-x", "name": "TeamX"}]
                })
            if call_count[0] <= 2:
                # My Drive /Documents resolves to my-docs-id
                return httpx.Response(200, json={
                    "files": [{"id": "my-docs-id", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
                })
            # Shared drive /Documents resolves to shared-docs-id
            return httpx.Response(200, json={
                "files": [{"id": "shared-docs-id", "name": "Documents", "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": FOLDER_MIME_TYPE}]
            })
        respx.get(url__startswith="https://www.googleapis.com").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            my_drive_id = await client._resolve_path("/My Drive/Documents")
            shared_id = await client._resolve_path("/Shared drives/TeamX/Documents")
            assert my_drive_id == "my-docs-id"
            assert shared_id == "shared-docs-id"
            assert my_drive_id != shared_id
        finally:
            await client.close()

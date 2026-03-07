"""Tests for Google Drive file operation tools."""

import base64
import json
import pytest
import httpx
import respx

from google_drive_mcp_server.drive_client import (
    DriveClient,
    DriveAPIError,
    PathCache,
    DRIVE_API_BASE,
    DRIVE_UPLOAD_BASE,
    FOLDER_MIME_TYPE,
)


def _files_response(files):
    """Build a standard files.list response."""
    return httpx.Response(200, json={"files": files})


def _folder_entry(id, name, modified="2024-01-01T00:00:00Z"):
    return {"id": id, "name": name, "modifiedTime": modified, "mimeType": FOLDER_MIME_TYPE}


def _file_entry(id, name, mime="text/plain", modified="2024-01-01T00:00:00Z"):
    return {"id": id, "name": name, "modifiedTime": modified, "mimeType": mime}


# Helper to mock path resolution for a single-level path
def _mock_resolve(path_name, file_id, is_folder=False):
    """Returns a respx side_effect that resolves a single path component."""
    mime = FOLDER_MIME_TYPE if is_folder else "text/plain"
    return httpx.Response(200, json={
        "files": [{"id": file_id, "name": path_name, "modifiedTime": "2024-01-01T00:00:00Z", "mimeType": mime}]
    })


@pytest.mark.asyncio
class TestListFiles:
    @respx.mock
    async def test_list_root(self):
        # Resolve root returns "root"
        # Then list children
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [
                    {"id": "f1", "name": "Documents", "mimeType": FOLDER_MIME_TYPE, "modifiedTime": "2024-01-01T00:00:00Z"},
                    {"id": "f2", "name": "report.md", "mimeType": "text/markdown", "size": "1024", "modifiedTime": "2024-01-02T00:00:00Z"},
                ]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.list_files("/")
            assert len(result) == 2
            assert result[0]["name"] == "Documents"
            assert result[0]["type"] == "folder"
            assert result[0]["size"] is None
            assert result[1]["name"] == "report.md"
            assert result[1]["type"] == "file"
            assert result[1]["size"] == 1024
        finally:
            await client.close()

    @respx.mock
    async def test_list_not_found(self):
        # Resolve path fails
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.list_files("/nonexistent")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()

    @respx.mock
    async def test_list_permission_denied(self):
        # Resolve succeeds but listing fails with 403
        call_count = 0
        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Resolve path
                return httpx.Response(200, json={
                    "files": [_folder_entry("folder-1", "restricted")]
                })
            else:
                # List children
                return httpx.Response(403, json={"error": {"message": "Access denied"}})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.list_files("/restricted")
            assert exc_info.value.error == "permission_denied"
        finally:
            await client.close()


@pytest.mark.asyncio
class TestReadFile:
    @respx.mock
    async def test_read_text_file(self):
        # Resolve path
        resolve_call = [0]
        def resolve_side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "report.md", "text/markdown")]
                })
            # Metadata request
            url_str = str(request.url)
            if "alt=media" in url_str:
                return httpx.Response(200, content=b"# Hello World")
            return httpx.Response(200, json={
                "id": "file-1", "name": "report.md", "mimeType": "text/markdown", "size": "13", "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-1\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=resolve_side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.read_file("/report.md")
            assert result["content"] == "# Hello World"
            assert result["binary"] is False
            assert result["mime_type"] == "text/markdown"
            assert result["etag"] == "\"etag-1\""
            assert result["size"] == 13
        finally:
            await client.close()

    @respx.mock
    async def test_read_binary_file(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-2", "logo.png", "image/png")]
                })
            url_str = str(request.url)
            if "alt=media" in url_str:
                return httpx.Response(200, content=b"\x89PNG")
            return httpx.Response(200, json={
                "id": "file-2", "name": "logo.png", "mimeType": "image/png", "size": "4", "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-2\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.read_file("/logo.png")
            assert result["binary"] is True
            assert result["mime_type"] == "image/png"
            decoded = base64.b64decode(result["content"])
            assert decoded == b"\x89PNG"
        finally:
            await client.close()

    @respx.mock
    async def test_read_file_not_found(self):
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.read_file("/nonexistent.txt")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()

    @respx.mock
    async def test_read_file_too_large(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-3", "bigfile.bin", "application/octet-stream")]
                })
            return httpx.Response(200, json={
                "id": "file-3", "name": "bigfile.bin", "mimeType": "application/octet-stream",
                "size": str(30 * 1024 * 1024), "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-3\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.read_file("/bigfile.bin")
            assert exc_info.value.error == "file_too_large"
        finally:
            await client.close()

    @respx.mock
    async def test_read_file_custom_max_size(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-4", "medium.bin", "application/octet-stream")]
                })
            return httpx.Response(200, json={
                "id": "file-4", "name": "medium.bin", "mimeType": "application/octet-stream",
                "size": "1024", "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-4\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token", max_file_size=512)
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.read_file("/medium.bin")
            assert exc_info.value.error == "file_too_large"
        finally:
            await client.close()


@pytest.mark.asyncio
class TestWriteFile:
    @respx.mock
    async def test_write_new_file(self):
        # Resolve path fails (file doesn't exist)
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        # Create folder resolution for parent "/" -> root
        # (no folder creation needed)

        # Upload
        respx.post(url__startswith=f"{DRIVE_UPLOAD_BASE}/files").mock(
            return_value=httpx.Response(201, json={
                "id": "new-file-id", "name": "new-report.md", "size": "12"
            }, headers={"etag": "\"new-etag\""})
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.write_file("/new-report.md", "# Report\n...")
            assert result["path"] == "/new-report.md"
            assert result["etag"] == "\"new-etag\""
            assert result["size"] == 12
        finally:
            await client.close()

    @respx.mock
    async def test_write_update_with_valid_etag(self):
        # Resolve path succeeds
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [_file_entry("file-1", "report.md")]
            })
        )
        # Update
        route = respx.patch(url__startswith=f"{DRIVE_UPLOAD_BASE}/files/file-1").mock(
            return_value=httpx.Response(200, json={
                "id": "file-1", "name": "report.md", "size": "7"
            }, headers={"etag": "\"new-etag\""})
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.write_file("/report.md", "updated", etag="\"abc123\"")
            assert result["etag"] == "\"new-etag\""
            # Verify If-Match header was sent
            assert route.calls[0].request.headers["if-match"] == "\"abc123\""
        finally:
            await client.close()

    @respx.mock
    async def test_write_with_stale_etag_conflict(self):
        # Resolve path succeeds
        resolve_call = [0]
        def resolve_side_effect(request):
            resolve_call[0] += 1
            url_str = str(request.url)
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "report.md")]
                })
            # Get current etag
            return httpx.Response(200, json={"id": "file-1"}, headers={"etag": "\"current-etag\""})

        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=resolve_side_effect)
        respx.patch(url__startswith=f"{DRIVE_UPLOAD_BASE}/files/file-1").mock(
            return_value=httpx.Response(412, json={"error": {"message": "Precondition failed"}})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.write_file("/report.md", "updated", etag="\"old-etag\"")
            assert exc_info.value.error == "conflict"
            assert exc_info.value.etag == "\"current-etag\""
        finally:
            await client.close()

    @respx.mock
    async def test_write_without_etag_no_if_match(self):
        # Resolve path succeeds
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [_file_entry("file-1", "report.md")]
            })
        )
        route = respx.patch(url__startswith=f"{DRIVE_UPLOAD_BASE}/files/file-1").mock(
            return_value=httpx.Response(200, json={
                "id": "file-1", "name": "report.md", "size": "7"
            }, headers={"etag": "\"new-etag\""})
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.write_file("/report.md", "updated")
            assert result["etag"] == "\"new-etag\""
            # Verify no If-Match header
            assert "if-match" not in route.calls[0].request.headers
        finally:
            await client.close()


@pytest.mark.asyncio
class TestDeleteFile:
    @respx.mock
    async def test_delete_existing_file(self):
        # Resolve path
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [_file_entry("file-1", "old-report.md")]
            })
        )
        respx.delete(url__startswith=f"{DRIVE_API_BASE}/files/file-1").mock(
            return_value=httpx.Response(204)
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.delete_file("/old-report.md")
            assert result == {"success": True}
        finally:
            await client.close()

    @respx.mock
    async def test_delete_not_found(self):
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        client = DriveClient(token="test-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.delete_file("/nonexistent.txt")
            assert exc_info.value.error == "not_found"
        finally:
            await client.close()


@pytest.mark.asyncio
class TestFileInfo:
    @respx.mock
    async def test_file_info(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "report.md", "text/markdown")]
                })
            return httpx.Response(200, json={
                "id": "file-1", "name": "report.md", "mimeType": "text/markdown",
                "size": "1024", "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-1\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.file_info("/report.md")
            assert result["name"] == "report.md"
            assert result["path"] == "/report.md"
            assert result["type"] == "file"
            assert result["size"] == 1024
            assert result["etag"] == "\"etag-1\""
            assert result["mime_type"] == "text/markdown"
        finally:
            await client.close()

    @respx.mock
    async def test_folder_info(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_folder_entry("folder-1", "Documents")]
                })
            return httpx.Response(200, json={
                "id": "folder-1", "name": "Documents", "mimeType": FOLDER_MIME_TYPE,
                "modifiedTime": "2024-01-01T00:00:00Z"
            }, headers={"etag": "\"etag-2\""})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.file_info("/Documents")
            assert result["name"] == "Documents"
            assert result["type"] == "folder"
            assert result["mime_type"] is None
        finally:
            await client.close()


@pytest.mark.asyncio
class TestCreateFolder:
    @respx.mock
    async def test_create_single_folder(self):
        # Resolve will fail (folder doesn't exist)
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={"files": []})
        )
        respx.post(f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(201, json={"id": "new-folder", "name": "NewFolder"})
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.create_folder("/NewFolder")
            assert result == {"path": "/NewFolder"}
        finally:
            await client.close()

    @respx.mock
    async def test_create_nested_folders(self):
        resolve_call = [0]
        def get_side_effect(request):
            nonlocal resolve_call
            resolve_call[0] += 1
            # All resolve attempts fail (folders don't exist yet)
            return httpx.Response(200, json={"files": []})

        post_call = [0]
        def post_side_effect(request):
            post_call[0] += 1
            names = ["Documents", "Reports", "2024"]
            idx = post_call[0] - 1
            return httpx.Response(201, json={"id": f"folder-{post_call[0]}", "name": names[idx]})

        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=get_side_effect)
        respx.post(f"{DRIVE_API_BASE}/files").mock(side_effect=post_side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.create_folder("/Documents/Reports/2024")
            assert result == {"path": "/Documents/Reports/2024"}
        finally:
            await client.close()

    @respx.mock
    async def test_create_folder_shared_drive(self):
        """create_folder handles /Shared drives/TeamX/... paths."""
        call_count = [0]
        def get_side_effect(request):
            call_count[0] += 1
            url_str = str(request.url)
            if call_count[0] == 1:
                # Initial _resolve_path for full path fails (folder doesn't exist)
                return httpx.Response(200, json={"files": []})
            if "drives" in url_str and "files" not in url_str:
                # _resolve_shared_drive
                return httpx.Response(200, json={
                    "drives": [{"id": "drive-1", "name": "TeamX"}]
                })
            # Subsequent resolve calls for intermediate folders fail
            return httpx.Response(200, json={"files": []})

        respx.get(url__startswith="https://www.googleapis.com").mock(side_effect=get_side_effect)
        respx.post(f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(201, json={"id": "new-folder-1", "name": "Reports"})
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.create_folder("/Shared drives/TeamX/Reports")
            assert result == {"path": "/Shared drives/TeamX/Reports"}
        finally:
            await client.close()

    @respx.mock
    async def test_create_existing_folder_idempotent(self):
        # Resolve succeeds (folder exists)
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(
            return_value=httpx.Response(200, json={
                "files": [_folder_entry("existing-folder", "ExistingFolder")]
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.create_folder("/ExistingFolder")
            assert result == {"path": "/ExistingFolder"}
        finally:
            await client.close()


@pytest.mark.asyncio
class TestMoveFile:
    @respx.mock
    async def test_move_to_different_folder(self):
        resolve_call = [0]
        def get_side_effect(request):
            resolve_call[0] += 1
            url_str = str(request.url)
            if resolve_call[0] == 1:
                # Resolve source: /Documents/report.md -> Documents
                return httpx.Response(200, json={
                    "files": [_folder_entry("doc-folder", "Documents")]
                })
            elif resolve_call[0] == 2:
                # Resolve source: report.md in Documents
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "report.md")]
                })
            elif resolve_call[0] == 3:
                # Resolve destination parent: /Archive
                return httpx.Response(200, json={
                    "files": [_folder_entry("archive-folder", "Archive")]
                })
            elif resolve_call[0] == 4:
                # Get current parents
                return httpx.Response(200, json={"parents": ["doc-folder"]})
            return httpx.Response(200, json={"files": []})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=get_side_effect)
        respx.patch(url__startswith=f"{DRIVE_API_BASE}/files/file-1").mock(
            return_value=httpx.Response(200, json={
                "id": "file-1", "name": "report.md"
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.move_file("/Documents/report.md", "/Archive/report.md")
            assert result == {"path": "/Archive/report.md"}
        finally:
            await client.close()

    @respx.mock
    async def test_rename_file(self):
        resolve_call = [0]
        def get_side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                # Resolve source: /Documents folder
                return httpx.Response(200, json={
                    "files": [_folder_entry("doc-folder", "Documents")]
                })
            elif resolve_call[0] == 2:
                # Resolve source: report.md
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "report.md")]
                })
            return httpx.Response(200, json={"files": []})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=get_side_effect)
        respx.patch(url__startswith=f"{DRIVE_API_BASE}/files/file-1").mock(
            return_value=httpx.Response(200, json={
                "id": "file-1", "name": "final-report.md"
            })
        )
        client = DriveClient(token="test-token")
        try:
            result = await client.move_file("/Documents/report.md", "/Documents/final-report.md")
            assert result == {"path": "/Documents/final-report.md"}
        finally:
            await client.close()


@pytest.mark.asyncio
class TestRetry:
    @respx.mock
    async def test_retry_on_429(self):
        """Test that 429 responses trigger retries with exponential backoff."""
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                # Resolve path
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "test.txt")]
                })
            elif resolve_call[0] == 2:
                # First metadata call - rate limited
                return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"message": "Throttled"}})
            else:
                # Retry succeeds
                return httpx.Response(200, json={
                    "id": "file-1", "name": "test.txt", "mimeType": "text/plain",
                    "size": "5", "modifiedTime": "2024-01-01T00:00:00Z"
                }, headers={"etag": "\"etag-1\""})
        route = respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="test-token")
        try:
            result = await client.file_info("/test.txt")
            assert result["name"] == "test.txt"
        finally:
            await client.close()

    @respx.mock
    async def test_auth_expired(self):
        resolve_call = [0]
        def side_effect(request):
            resolve_call[0] += 1
            if resolve_call[0] == 1:
                return httpx.Response(200, json={
                    "files": [_file_entry("file-1", "test.txt")]
                })
            return httpx.Response(401, json={"error": {"message": "Token expired"}})
        respx.get(url__startswith=f"{DRIVE_API_BASE}/files").mock(side_effect=side_effect)
        client = DriveClient(token="expired-token")
        try:
            with pytest.raises(DriveAPIError) as exc_info:
                await client.file_info("/test.txt")
            assert exc_info.value.error == "auth_expired"
        finally:
            await client.close()

"""Async Google Drive API v3 client using httpx."""

import asyncio
import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

# Default maximum file size for read operations (25 MB)
DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024

# Mime types considered text
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_EXACT = (
    "application/json",
    "application/xml",
    "application/yaml",
    "application/x-yaml",
    "application/javascript",
    "application/typescript",
    "application/xhtml+xml",
    "application/sql",
    "application/graphql",
    "application/ld+json",
    "application/x-sh",
    "application/x-python",
)

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def is_text_mime(mime_type: str | None) -> bool:
    """Determine if a MIME type represents text content."""
    if not mime_type:
        return False
    mime_lower = mime_type.lower().split(";")[0].strip()
    if any(mime_lower.startswith(p) for p in TEXT_MIME_PREFIXES):
        return True
    return mime_lower in TEXT_MIME_EXACT


class DriveAPIError(Exception):
    """Structured error from Google Drive API operations."""

    def __init__(
        self,
        error: str,
        message: str,
        status_code: int | None = None,
        etag: str | None = None,
    ):
        self.error = error
        self.message = message
        self.status_code = status_code
        self.etag = etag
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"error": self.error, "message": self.message}
        if self.etag:
            result["etag"] = self.etag
        return result


def _map_error(response: httpx.Response, context: str = "") -> DriveAPIError:
    """Map HTTP status codes to structured errors."""
    status = response.status_code
    try:
        body = response.json()
        detail = (
            body.get("error", {}).get("message", response.text[:200])
            if isinstance(body.get("error"), dict)
            else str(body.get("error", response.text[:200]))
        )
    except Exception:
        detail = response.text[:200] if response.text else "Unknown error"

    prefix = f"{context}: " if context else ""

    if status == 401:
        return DriveAPIError(
            "auth_expired",
            f"{prefix}Authentication token has expired or is invalid. {detail}",
            status,
        )
    elif status == 403:
        return DriveAPIError(
            "permission_denied",
            f"{prefix}Access denied. {detail}",
            status,
        )
    elif status == 404:
        return DriveAPIError(
            "not_found",
            f"{prefix}Resource not found. {detail}",
            status,
        )
    elif status == 412:
        # Precondition failed - ETag mismatch
        return DriveAPIError(
            "conflict",
            f"{prefix}File has been modified (ETag mismatch). {detail}",
            status,
        )
    elif status == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        return DriveAPIError(
            "rate_limited",
            f"{prefix}Rate limited. Retry after {retry_after} seconds. {detail}",
            status,
        )
    else:
        return DriveAPIError(
            "api_error",
            f"{prefix}Drive API error (HTTP {status}): {detail}",
            status,
        )


class PathCache:
    """Per-session cache for path-to-ID resolution."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def get(self, path: str) -> str | None:
        return self._cache.get(self._normalise(path))

    def set(self, path: str, file_id: str) -> None:
        self._cache[self._normalise(path)] = file_id

    def invalidate(self, path: str) -> None:
        key = self._normalise(path)
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    @staticmethod
    def _normalise(path: str) -> str:
        """Normalise path for cache key (lowercase for case-insensitive matching)."""
        return path.strip().rstrip("/").lower()


class DriveClient:
    """Async client for Google Drive API v3 operations."""

    def __init__(
        self,
        token: str,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        path_cache: PathCache | None = None,
    ):
        self.token = token
        self.max_file_size = max_file_size
        self._cache = path_cache or PathCache()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict | None = None,
        content: bytes | None = None,
        params: dict[str, str] | None = None,
        follow_redirects: bool = True,
        max_retries: int = 2,
    ) -> httpx.Response:
        """Make a request with automatic retry on 429 with exponential backoff."""
        all_headers = self._headers(headers)
        for attempt in range(max_retries + 1):
            response = await self._client.request(
                method,
                url,
                headers=all_headers,
                json=json,
                content=content,
                params=params,
                follow_redirects=follow_redirects,
            )
            if response.status_code == 429 and attempt < max_retries:
                retry_after = int(response.headers.get("Retry-After", str(2 ** attempt)))
                logger.warning(
                    f"Rate limited (429), retrying after {retry_after}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(retry_after)
                continue
            return response
        return response  # Return last response if all retries exhausted

    # ---- Path Resolution ----

    async def _resolve_path(self, path: str) -> str:
        """Resolve a human-readable path to a Google Drive file ID.

        Supports:
        - / or empty → root (My Drive)
        - /My Drive/... → user's root
        - /Shared drives/TeamName/... → shared/team drives
        - Case-insensitive folder navigation
        - Duplicate filenames: returns most recently modified file
        """
        clean = path.strip().rstrip("/")
        if not clean or clean == "/":
            return "root"

        # Check cache
        cached = self._cache.get(clean)
        if cached:
            return cached

        # Remove leading slash
        if clean.startswith("/"):
            clean = clean[1:]

        parts = clean.split("/")

        # Handle /My Drive prefix
        if parts[0].lower() == "my drive":
            parts = parts[1:]
            if not parts:
                self._cache.set(path, "root")
                return "root"
            current_id = "root"
        # Handle /Shared drives/TeamName/...
        elif parts[0].lower() == "shared drives":
            if len(parts) < 2:
                raise DriveAPIError(
                    "not_found",
                    "Path '/Shared drives' requires a drive name (e.g., '/Shared drives/TeamName')",
                )
            drive_name = parts[1]
            current_id = await self._resolve_shared_drive(drive_name)
            parts = parts[2:]
            if not parts:
                self._cache.set(path, current_id)
                return current_id
        else:
            current_id = "root"

        # Walk the folder tree
        accumulated_path = ""
        for i, part in enumerate(parts):
            accumulated_path += "/" + part
            cached_id = self._cache.get(accumulated_path)
            if cached_id:
                current_id = cached_id
                continue

            current_id = await self._resolve_child(current_id, part, accumulated_path)
            self._cache.set(accumulated_path, current_id)

        # Cache the full path
        self._cache.set(path, current_id)
        return current_id

    async def _resolve_shared_drive(self, drive_name: str) -> str:
        """Resolve a shared drive name to its ID."""
        url = f"{DRIVE_API_BASE}/drives"
        response = await self._request("GET", url, params={"pageSize": "100"})
        if response.status_code != 200:
            raise _map_error(response, f"resolve shared drive '{drive_name}'")

        drives = response.json().get("drives", [])
        for drive in drives:
            if drive["name"].lower() == drive_name.lower():
                return drive["id"]

        raise DriveAPIError(
            "not_found",
            f"Shared drive '{drive_name}' not found",
        )

    async def _resolve_child(self, parent_id: str, name: str, full_path: str) -> str:
        """Resolve a child by name within a parent folder.

        Case-insensitive. Returns most recently modified file if duplicates exist.
        """
        # Use files.list with parent filter and name filter
        q = f"'{parent_id}' in parents and trashed = false"
        url = f"{DRIVE_API_BASE}/files"
        params = {
            "q": q,
            "fields": "files(id,name,modifiedTime,mimeType)",
            "pageSize": "1000",
            "orderBy": "modifiedTime desc",
        }

        # Include shared drive support
        if parent_id != "root":
            params["includeItemsFromAllDrives"] = "true"
            params["supportsAllDrives"] = "true"

        response = await self._request("GET", url, params=params)
        if response.status_code != 200:
            raise _map_error(response, f"resolve path '{full_path}'")

        files = response.json().get("files", [])
        # Case-insensitive name match, return most recently modified
        name_lower = name.lower()
        for f in files:
            if f["name"].lower() == name_lower:
                return f["id"]

        raise DriveAPIError("not_found", f"Path not found: {full_path}")

    # ---- File Operations ----

    async def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        """List files in a folder."""
        folder_id = await self._resolve_path(path)

        q = f"'{folder_id}' in parents and trashed = false"
        url = f"{DRIVE_API_BASE}/files"
        params: dict[str, str] = {
            "q": q,
            "fields": "files(id,name,mimeType,size,modifiedTime,parents)",
            "pageSize": "1000",
            "orderBy": "name",
        }
        if folder_id != "root":
            params["includeItemsFromAllDrives"] = "true"
            params["supportsAllDrives"] = "true"

        response = await self._request("GET", url, params=params)
        if response.status_code != 200:
            raise _map_error(response, f"list_files({path})")

        data = response.json()
        entries = []
        # Normalise the base path
        base_path = path.strip().rstrip("/")
        if not base_path or base_path == "/":
            base_path = ""

        for item in data.get("files", []):
            is_folder = item.get("mimeType") == FOLDER_MIME_TYPE
            item_path = f"{base_path}/{item['name']}"

            # Get etag for each file
            etag = await self._get_etag(item["id"])

            entry: dict[str, Any] = {
                "name": item["name"],
                "path": item_path,
                "type": "folder" if is_folder else "file",
                "size": int(item["size"]) if item.get("size") else None,
                "modified": item.get("modifiedTime"),
                "etag": etag,
            }
            entries.append(entry)
        return entries

    async def _get_etag(self, file_id: str) -> str | None:
        """Get the ETag for a file by ID using a HEAD-like request."""
        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params = {"fields": "id", "supportsAllDrives": "true"}
        response = await self._request("GET", url, params=params)
        if response.status_code == 200:
            return response.headers.get("etag")
        return None

    async def read_file(self, path: str) -> dict[str, Any]:
        """Read file content and metadata."""
        file_id = await self._resolve_path(path)

        # Get metadata
        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params = {
            "fields": "id,name,mimeType,size,modifiedTime",
            "supportsAllDrives": "true",
        }
        meta_response = await self._request("GET", url, params=params)
        if meta_response.status_code != 200:
            raise _map_error(meta_response, f"read_file({path})")

        meta = meta_response.json()
        file_size = int(meta.get("size", 0))
        mime_type = meta.get("mimeType", "application/octet-stream")
        etag = meta_response.headers.get("etag")

        # Check file size limit
        if file_size > self.max_file_size:
            raise DriveAPIError(
                "file_too_large",
                f"File size ({file_size} bytes) exceeds maximum allowed size ({self.max_file_size} bytes)",
            )

        # Download content
        content_url = f"{DRIVE_API_BASE}/files/{file_id}"
        content_params = {"alt": "media", "supportsAllDrives": "true"}
        content_response = await self._request("GET", content_url, params=content_params)

        if content_response.status_code != 200:
            raise _map_error(content_response, f"read_file({path}) content")

        raw_content = content_response.content
        is_binary = not is_text_mime(mime_type)

        if is_binary:
            content_str = base64.b64encode(raw_content).decode("ascii")
        else:
            content_str = raw_content.decode("utf-8", errors="replace")

        return {
            "content": content_str,
            "etag": etag,
            "mime_type": mime_type,
            "size": file_size,
            "binary": is_binary,
        }

    async def write_file(
        self, path: str, content: str, etag: str | None = None
    ) -> dict[str, Any]:
        """Create or update a file."""
        clean = path.strip()
        if not clean.startswith("/"):
            clean = "/" + clean

        # Split into parent path and filename
        if "/" in clean[1:]:
            parent_path = clean.rsplit("/", 1)[0]
            file_name = clean.rsplit("/", 1)[1]
        else:
            parent_path = "/"
            file_name = clean[1:]

        # Try to resolve existing file first
        existing_id = None
        try:
            existing_id = await self._resolve_path(clean)
        except DriveAPIError:
            pass

        content_bytes = content.encode("utf-8")

        if existing_id:
            # Update existing file
            url = f"{DRIVE_UPLOAD_BASE}/files/{existing_id}"
            params: dict[str, str] = {
                "uploadType": "media",
                "supportsAllDrives": "true",
            }
            headers: dict[str, str] = {"Content-Type": "application/octet-stream"}
            if etag:
                headers["If-Match"] = etag

            response = await self._request(
                "PATCH", url, headers=headers, content=content_bytes, params=params
            )

            if response.status_code == 412:
                err = _map_error(response, f"write_file({path})")
                # Try to get current etag
                try:
                    current_url = f"{DRIVE_API_BASE}/files/{existing_id}"
                    current_response = await self._request(
                        "GET",
                        current_url,
                        params={"fields": "id", "supportsAllDrives": "true"},
                    )
                    if current_response.status_code == 200:
                        err.etag = current_response.headers.get("etag")
                except Exception:
                    pass
                raise err

            if response.status_code != 200:
                raise _map_error(response, f"write_file({path})")

            new_etag = response.headers.get("etag")
            data = response.json()
            return {
                "path": clean,
                "etag": new_etag,
                "size": int(data.get("size", len(content_bytes))),
            }
        else:
            # Create new file - ensure parent folder exists
            parent_id = await self._ensure_folder(parent_path)

            # Create file with multipart upload
            metadata = {
                "name": file_name,
                "parents": [parent_id],
            }

            # Use simple upload with metadata
            url = f"{DRIVE_UPLOAD_BASE}/files"
            params = {
                "uploadType": "multipart",
                "supportsAllDrives": "true",
            }

            # Build multipart body
            import json as json_mod
            boundary = "boundary_fastmcp_upload"
            body = (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json_mod.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode("utf-8") + content_bytes + f"\r\n--{boundary}--".encode("utf-8")

            headers = {
                "Content-Type": f"multipart/related; boundary={boundary}",
            }

            response = await self._request(
                "POST", url, headers=headers, content=body, params=params
            )

            if response.status_code not in (200, 201):
                raise _map_error(response, f"write_file({path})")

            new_etag = response.headers.get("etag")
            data = response.json()

            # Cache the new file path
            self._cache.set(clean, data["id"])

            return {
                "path": clean,
                "etag": new_etag,
                "size": int(data.get("size", len(content_bytes))),
            }

    async def _ensure_folder(self, path: str) -> str:
        """Ensure a folder exists, creating intermediates as needed. Returns folder ID."""
        try:
            return await self._resolve_path(path)
        except DriveAPIError:
            # Create the folder
            result = await self.create_folder(path)
            return await self._resolve_path(path)

    async def delete_file(self, path: str) -> dict[str, bool]:
        """Delete a file permanently."""
        file_id = await self._resolve_path(path)

        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params = {"supportsAllDrives": "true"}
        response = await self._request("DELETE", url, params=params)

        if response.status_code == 204:
            self._cache.invalidate(path)
            return {"success": True}
        raise _map_error(response, f"delete_file({path})")

    async def file_info(self, path: str) -> dict[str, Any]:
        """Get file metadata without content."""
        file_id = await self._resolve_path(path)

        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params = {
            "fields": "id,name,mimeType,size,modifiedTime",
            "supportsAllDrives": "true",
        }
        response = await self._request("GET", url, params=params)

        if response.status_code != 200:
            raise _map_error(response, f"file_info({path})")

        item = response.json()
        is_folder = item.get("mimeType") == FOLDER_MIME_TYPE
        mime_type = item.get("mimeType") if not is_folder else None
        etag = response.headers.get("etag")

        # Normalise path
        clean = path.strip()
        if not clean.startswith("/"):
            clean = "/" + clean

        return {
            "name": item["name"],
            "path": clean,
            "type": "folder" if is_folder else "file",
            "size": int(item["size"]) if item.get("size") else None,
            "modified": item.get("modifiedTime"),
            "etag": etag,
            "mime_type": mime_type,
        }

    async def create_folder(self, path: str) -> dict[str, str]:
        """Create a folder including intermediate folders."""
        clean = path.strip()
        if not clean.startswith("/"):
            clean = "/" + clean
        clean = clean.rstrip("/")

        # Check if already exists
        try:
            existing_id = await self._resolve_path(clean)
            return {"path": clean}
        except DriveAPIError:
            pass

        parts_str = clean[1:] if clean.startswith("/") else clean
        # Handle My Drive prefix
        parts = parts_str.split("/")
        if parts[0].lower() == "my drive":
            parts = parts[1:]
        current_id = "root"
        current_path = ""

        for part in parts:
            current_path += "/" + part
            # Check cache/resolve first
            try:
                current_id = await self._resolve_path(current_path)
                continue
            except DriveAPIError:
                pass

            # Create the folder
            metadata = {
                "name": part,
                "mimeType": FOLDER_MIME_TYPE,
                "parents": [current_id],
            }
            url = f"{DRIVE_API_BASE}/files"
            params = {"supportsAllDrives": "true"}
            response = await self._request(
                "POST",
                url,
                headers={"Content-Type": "application/json"},
                json=metadata,
                params=params,
            )

            if response.status_code in (200, 201):
                data = response.json()
                current_id = data["id"]
                self._cache.set(current_path, current_id)
            else:
                raise _map_error(response, f"create_folder({path})")

        return {"path": clean}

    async def move_file(self, source: str, destination: str) -> dict[str, str]:
        """Move or rename a file."""
        file_id = await self._resolve_path(source)

        # Parse destination
        dest_clean = destination.strip()
        if not dest_clean.startswith("/"):
            dest_clean = "/" + dest_clean
        dest_clean = dest_clean.rstrip("/")

        dest_parts = dest_clean.rsplit("/", 1)
        if len(dest_parts) == 2 and dest_parts[0]:
            dest_parent_path = dest_parts[0]
            dest_name = dest_parts[1]
        else:
            dest_parent_path = "/"
            dest_name = dest_parts[-1]

        # Parse source parent
        source_clean = source.strip()
        if not source_clean.startswith("/"):
            source_clean = "/" + source_clean
        source_parent = source_clean.rsplit("/", 1)[0] or "/"

        # Build update body and params
        metadata: dict[str, Any] = {"name": dest_name}

        url = f"{DRIVE_API_BASE}/files/{file_id}"
        params: dict[str, str] = {"supportsAllDrives": "true"}

        # If moving to a different folder
        if dest_parent_path.lower() != source_parent.lower():
            # Resolve destination parent
            dest_parent_id = await self._resolve_path(dest_parent_path)

            # Get current parents
            info_url = f"{DRIVE_API_BASE}/files/{file_id}"
            info_params = {"fields": "parents", "supportsAllDrives": "true"}
            info_response = await self._request("GET", info_url, params=info_params)
            if info_response.status_code != 200:
                raise _map_error(
                    info_response, f"move_file({source} -> {destination}) get parents"
                )
            current_parents = info_response.json().get("parents", [])
            params["addParents"] = dest_parent_id
            params["removeParents"] = ",".join(current_parents)

        response = await self._request(
            "PATCH",
            url,
            headers={"Content-Type": "application/json"},
            json=metadata,
            params=params,
        )

        if response.status_code != 200:
            raise _map_error(response, f"move_file({source} -> {destination})")

        # Invalidate old cache entry, add new one
        self._cache.invalidate(source)
        self._cache.set(dest_clean, file_id)

        return {"path": dest_clean}

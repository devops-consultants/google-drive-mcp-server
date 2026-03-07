# Google Drive MCP Server

An open-source MCP (Model Context Protocol) server that provides file operations for Google Drive via Streamable HTTP transport. Designed for containerized AI agents — not desktop STDIO clients.

## Overview

This server exposes Google Drive file operations as MCP tools, allowing AI agents to list, read, write, delete, move files and create folders in Google Drive. It uses path-based addressing (e.g., `/My Drive/docs/report.md`) and resolves paths to Google Drive file IDs internally.

The server is **stateless** — it receives a Google OAuth access token in the `Authorization: Bearer <token>` header per MCP session and forwards requests to the Google Drive API v3. The calling application manages the OAuth lifecycle.

## Features

- **7 file operation tools**: list_files, read_file, write_file, delete_file, file_info, create_folder, move_file
- **Path-based interface**: Human-readable paths instead of opaque file IDs
- **Streamable HTTP transport**: Compatible with containerized MCP clients
- **Bearer token auth**: Stateless, per-session authentication
- **ETag concurrency**: Optimistic conflict detection for safe parallel writes
- **Text and binary support**: UTF-8 for text files, base64 for binary
- **Shared drives**: Support for team/shared drives via `/Shared drives/TeamName/...`

## Deployment

### Docker

```bash
docker pull ghcr.io/devops-consultants/google-drive-mcp-server:latest
docker run -p 8080:8080 ghcr.io/devops-consultants/google-drive-mcp-server:latest
```

### Docker Compose

```bash
docker compose up
```

### Local Development

Requires Python 3.12+.

```bash
pip install -r requirements.txt
pip install -e ".[dev]"  # test dependencies
python -m google_drive_mcp_server
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server listening port |
| `HOST` | `0.0.0.0` | Server bind address |
| `MAX_FILE_SIZE` | `26214400` (25MB) | Maximum file size for read operations (bytes) |

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mcp` | POST | MCP Streamable HTTP endpoint |
| `/health` | GET | Health check — returns `{"status": "ok"}` |

## Tool Reference

### list_files

List files and folders in a Google Drive directory.

**Parameters:**
- `path` (string, default: `"/"`): Directory path to list

**Returns:** Array of entries with `name`, `path`, `type` ("file" or "folder"), `size`, `modified`.

### read_file

Read a file's content and metadata.

**Parameters:**
- `path` (string, required): Path to the file

**Returns:** `content` (UTF-8 or base64), `etag`, `mime_type`, `size`, `binary` (boolean).

### write_file

Create or update a file with optional conflict detection.

**Parameters:**
- `path` (string, required): Path where the file should be written
- `content` (string, required): File content (text)
- `etag` (string, optional): ETag for optimistic concurrency control

**Returns:** `path`, `etag`, `size`.

### delete_file

Permanently delete a file (not trash).

**Parameters:**
- `path` (string, required): Path to the file to delete

**Returns:** `{"success": true}`.

### file_info

Get file or folder metadata without downloading content.

**Parameters:**
- `path` (string, required): Path to the file or folder

**Returns:** `name`, `path`, `type`, `size`, `modified`, `etag`, `mime_type`.

### create_folder

Create a folder (including intermediate folders).

**Parameters:**
- `path` (string, required): Path of the folder to create

**Returns:** `{"path": "<created path>"}`.

### move_file

Move or rename a file.

**Parameters:**
- `source` (string, required): Current path of the file
- `destination` (string, required): New path for the file

**Returns:** `{"path": "<new path>"}`.

## Path Resolution

The server resolves human-readable paths to Google Drive file IDs by walking the folder tree:

- **`/`** or **`/My Drive`** — user's root drive
- **`/My Drive/Documents/report.md`** — file in user's drive
- **`/Shared drives/TeamName/...`** — shared/team drives
- Paths are **case-insensitive** for folder navigation (matching Google Drive behavior)
- **Duplicate filenames**: When multiple files share the same name in a folder, the most recently modified file is returned
- Resolved path-to-ID mappings are **cached per session** to reduce API calls

## Error Handling

Google Drive API errors are mapped to structured error responses:

| HTTP Status | Error Code | Description |
|-------------|-----------|-------------|
| 401 | `auth_expired` | Token expired or invalid |
| 403 | `permission_denied` | Access denied |
| 404 | `not_found` | File/folder not found |
| 412 | `conflict` | ETag mismatch (includes current etag) |
| 429 | `rate_limited` | Rate limited (automatic retry with exponential backoff) |
| — | `file_too_large` | File exceeds configurable size limit |

## Authentication

The server expects a Google OAuth access token in the `Authorization` header:

```
Authorization: Bearer <google-oauth-access-token>
```

The token must have the `https://www.googleapis.com/auth/drive` scope. The server does **not** handle OAuth consent or token refresh — the calling application is responsible for providing a valid token.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

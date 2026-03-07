# Google Drive MCP Server - Project Overview

## Purpose
Open-source MCP (Model Context Protocol) server that provides file operations for Google Drive via Streamable HTTP transport. Designed for containerized AI agents, not desktop STDIO clients. The server is a stateless proxy — it receives a Google OAuth access token in the `Authorization: Bearer <token>` header per MCP session and forwards requests to Google Drive API v3.

## Tech Stack
- **Python 3.12+** with **FastMCP** (Streamable HTTP mode at `/mcp`)
- **httpx** (async) for Google Drive API v3 calls — NOT `google-api-python-client` (it's sync)
- **uvicorn** as the ASGI server (used internally by FastMCP)
- **Docker** for deployment (image at `ghcr.io/devops-consultants/google-drive-mcp-server`)
- **pytest** + **pytest-asyncio** + **respx** for testing

## Key Design Decisions
- **Stateless auth**: Bearer token extracted per session via FastMCP middleware, never stored
- **Path-based interface**: Agents use paths like `/My Drive/docs/report.md`, server resolves to Drive file IDs by walking folder tree via `files.list` queries
- **Per-session path cache**: Resolved path→ID mappings cached within a session, discarded on session end. Cache keys include drive prefix to avoid cross-drive collisions
- **ETag optimistic concurrency**: Reads return ETags; writes accept optional `etag` param for conflict detection via `If-Match` header
- **Text-first, binary-aware**: Text files as UTF-8, binary as base64
- **Server-side name filtering**: `_resolve_child()` uses Drive API `name = 'x'` filter with client-side case-insensitive fallback
- **Pagination**: Both `list_files()` and `_resolve_child()` follow `nextPageToken`

## Codebase Structure
```
google_drive_mcp_server/
├── __init__.py          # Package init
├── __main__.py          # Entry point for `python -m google_drive_mcp_server`
├── server.py            # FastMCP server, 7 MCP tools, auth middleware, health endpoint
└── drive_client.py      # Async Google Drive API client (DriveClient, PathCache, error mapping)
tests/
├── conftest.py          # Shared fixtures
├── test_auth.py         # Bearer token extraction tests
├── test_health.py       # Health endpoint ASGI test
├── test_drive_client.py # Unit tests: is_text_mime, PathCache, _map_error, path resolution
└── test_file_operations.py  # Integration tests: all 7 tools, retry, error cases
```

## MCP Tools (all path-based)
- `list_files(path)` — list folder contents (no etag in results)
- `read_file(path)` — read content + metadata (etag, mime_type, size, binary)
- `write_file(path, content, etag?)` — create/update with optional conflict detection
- `delete_file(path)` — permanent delete (not trash)
- `file_info(path)` — metadata without content (includes etag)
- `create_folder(path)` — create folder including intermediates, supports shared drives
- `move_file(source, destination)` — move/rename

## Endpoints
- `POST /mcp` — MCP Streamable HTTP endpoint
- `GET /health` — returns `{"status": "ok"}`

## Environment Variables
- `PORT` (default 8080) — server listening port
- `HOST` (default 0.0.0.0) — server bind address
- `MAX_FILE_SIZE` (default 25MB) — max file size for read operations

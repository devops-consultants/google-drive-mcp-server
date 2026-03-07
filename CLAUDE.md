# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Drive MCP server built with Python FastMCP, exposing file operations via Streamable HTTP transport. Designed for containerized AI agents (not desktop STDIO clients). The server is a stateless proxy — it receives a Google OAuth access token in the `Authorization: Bearer <token>` header per MCP session and forwards requests to Google Drive API v3.

## Tech Stack

- **Python** with **FastMCP** (Streamable HTTP mode at `/mcp`)
- **httpx** (async) for Google Drive API v3 calls — not `google-api-python-client` (it's sync)
- **uvicorn** as the ASGI server
- **Docker** for deployment (image at `ghcr.io/devops-consultants/google-drive-mcp-server`)

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run server locally (default port 8080)
python -m google_drive_mcp_server
# or with custom port:
PORT=9090 python -m google_drive_mcp_server

# Run tests
pytest
pytest tests/test_specific.py           # single file
pytest tests/test_specific.py::test_fn  # single test

# Docker
docker compose up                       # local dev
docker build -t google-drive-mcp-server .
```

## Architecture

### Key Design Decisions

- **Stateless auth**: Bearer token extracted per session, never stored or refreshed. The calling application manages OAuth lifecycle.
- **Path-based interface**: Agents use paths like `/My Drive/docs/report.md`. The server resolves paths to Google Drive file IDs internally by walking the folder tree via `files.list` queries.
- **Per-session path cache**: Resolved path→ID mappings cached within a session to reduce API calls. Cache discarded on session end.
- **ETag optimistic concurrency**: Reads return ETags; writes accept optional `etag` param for conflict detection via `If-Match` header.
- **Text-first, binary-aware**: Text files as UTF-8, binary files as base64 with `binary: true` and `mime_type`.
- **httpx over google-api-python-client**: Async-native, lightweight, full control over headers for ETag/If-Match.

### MCP Tools

All tools use path-based addressing:
- `list_files(path)` — list folder contents
- `read_file(path)` — read content + metadata (etag, mime_type, size, binary flag)
- `write_file(path, content, etag?)` — create/update with optional conflict detection
- `delete_file(path)` — permanent delete (not trash)
- `file_info(path)` — metadata without content
- `create_folder(path)` — create folder including intermediates
- `move_file(source, destination)` — move/rename

### Path Resolution

- `/My Drive/...` — user's root drive
- `/Shared drives/TeamName/...` — shared/team drives
- Case-insensitive folder navigation (matching Google Drive behavior)
- Duplicate filenames: return most recently modified file

### Error Mapping

Google Drive HTTP errors mapped to structured tool errors:
- 404 → `not_found`
- 403 → `permission_denied`
- 401 → `auth_expired`
- 429 → `rate_limited` (with exponential backoff retry)
- ETag mismatch → `conflict` (includes current etag)
- File > 25MB (configurable) → `file_too_large`

### Endpoints

- `POST /mcp` — MCP Streamable HTTP endpoint
- `GET /health` — returns `{"status": "ok"}`

## OpenSpec

Design artifacts are in `openspec/changes/google-drive-mcp-server/`. The `tasks.md` contains the implementation checklist.

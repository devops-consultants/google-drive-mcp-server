# Proposal: Google Drive MCP Server

## Problem

AI agents running in ephemeral containers (like the errand task-runner) have no access to cloud storage. Users store documents, data, and collaborative content in Google Drive, but agents can only work with git repositories and local files. This prevents agents from reading source materials, producing deliverables in shared folders, or collaborating across tasks via shared cloud documents.

There is no official Google Drive MCP server that supports Streamable HTTP transport — existing community implementations are STDIO-only, designed for desktop clients like Claude Desktop, not containerized agents.

## Solution

Build an open-source Google Drive MCP server using FastMCP with Streamable HTTP transport. The server provides path-based file operations (list, read, write, delete, move, create folder) against the Google Drive API, with stateless Bearer token authentication per session.

The server is designed to be deployed as a standalone service alongside application backends (like errand) that manage OAuth token lifecycle. It receives a pre-refreshed access token in the Authorization header of each MCP session — it never stores or refreshes tokens itself.

### Key Design Decisions

- **Streamable HTTP transport** — compatible with containerized MCP clients that cannot run STDIO subprocesses
- **Stateless auth** — Bearer token per session, no token storage, no OAuth flow in the server itself
- **Path-based interface** — agents use human-readable paths like `/My Drive/docs/report.md` instead of opaque Google Drive file IDs; the server resolves paths to IDs internally
- **Optimistic concurrency** — read operations return ETags, write operations accept an optional ETag parameter; mismatches return a conflict error rather than silently overwriting
- **Multi-session concurrent access** — multiple agents can connect simultaneously with different tokens; no shared state between sessions
- **Permission error handling** — requests full Drive scope, but gracefully returns clear error messages when the authenticated user lacks access to specific files/folders
- **Text-first, binary-aware** — text files returned as UTF-8 strings, binary files as base64-encoded content with mime_type metadata

### Tool Interface

All tools use path-based addressing:

- `list_files(path)` — list contents of a folder
- `read_file(path)` — read file content + metadata (etag, mime_type, size)
- `write_file(path, content, etag?)` — create or update a file with optional conflict detection
- `delete_file(path)` — delete a file
- `file_info(path)` — get metadata without content
- `create_folder(path)` — create a folder (including intermediate folders)
- `move_file(source, destination)` — move/rename a file

### Path Resolution

Google Drive is ID-based internally, so the server walks the folder tree to resolve paths:

- `/My Drive/...` — user's root drive
- `/Shared drives/TeamName/...` — shared/team drives
- Paths are case-insensitive for folder navigation (matching Google Drive behavior)

## Tech Stack

- **Python** with **FastMCP** (Streamable HTTP mode)
- **Google Drive API v3** via `google-api-python-client` or direct HTTP with `httpx`
- **Docker** container image published to `ghcr.io/devops-consultants/google-drive-mcp-server`
- CI/CD via GitHub Actions (build image, push to GHCR)

## Non-Goals

- OAuth consent flow — the calling application (errand) handles this
- Token refresh — the calling application provides fresh tokens
- Google Docs/Sheets native format conversion (future enhancement)
- File sharing/permission management
- Real-time file watching or change notifications

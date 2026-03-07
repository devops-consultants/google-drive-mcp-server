## Context

This is a greenfield project — a standalone MCP server that exposes Google Drive operations via Streamable HTTP transport. It will be deployed alongside the errand backend (as a K8s Deployment/Service or an Apple Containerization container) and consumed by task-runner agents via the MCP protocol.

The server is stateless — it receives a Google OAuth access token in the Authorization header of each MCP session and proxies requests to the Google Drive API v3. Multiple concurrent agents can connect simultaneously with different tokens.

Google Drive is ID-based internally (files and folders are addressed by opaque IDs), but agents work with human-readable paths. The server must resolve paths to IDs transparently.

## Goals / Non-Goals

**Goals:**

- Provide a reliable, path-based file operations interface over Google Drive API v3
- Support concurrent multi-session access with independent Bearer tokens
- Handle optimistic concurrency via ETags for safe parallel writes
- Return clear, actionable error messages for permission and conflict errors
- Be deployable as a standalone Docker container with no external dependencies

**Non-Goals:**

- OAuth consent flow or token refresh (the calling application handles this)
- Google Docs/Sheets native format conversion (future enhancement)
- File sharing, permissions management, or admin operations
- Real-time change notifications or file watching
- Caching or local state between requests

## Decisions

### 1. FastMCP with Streamable HTTP transport

**Choice:** Python FastMCP in HTTP mode (`mcp.run(transport="streamable-http")`)

**Rationale:** Consistent with the errand ecosystem (Python, FastMCP for the existing errand MCP server). Streamable HTTP is required because task-runner containers only support HTTP-based MCP servers, not STDIO. FastMCP handles session management, tool registration, and transport automatically.

**Alternative considered:** TypeScript MCP SDK — larger MCP ecosystem but would introduce a second language into the errand stack.

### 2. Stateless Bearer token authentication

**Choice:** Extract the access token from the `Authorization: Bearer <token>` header on session initialization. Use it for all Google Drive API calls within that session. Never store tokens.

**Rationale:** The calling application (errand worker) manages OAuth lifecycle — consent, storage, refresh. The MCP server is a pure proxy. This avoids credential storage, simplifies the server, and naturally supports multi-tenancy (different tokens = different Drive accounts).

**Alternative considered:** Server-side token storage with client IDs — adds complexity, state management, and security surface for no benefit.

### 3. Path-to-ID resolution with caching per session

**Choice:** Resolve paths by walking the folder tree via `files.list` queries with parent filters. Cache resolved path→ID mappings within a session to avoid redundant API calls.

**Rationale:** Google Drive has no native path-based API. Walking the tree is necessary. Per-session caching is safe because a session represents a single agent's work — its own operations are the primary source of path changes. The cache is discarded when the session ends.

**Alternative considered:** Global path cache across sessions — risks stale mappings when external users modify the Drive. Per-session caching is safer and simpler.

### 4. httpx for Google Drive API calls

**Choice:** Use `httpx.AsyncClient` with direct HTTP calls to the Drive API v3 REST endpoints, rather than the `google-api-python-client` library.

**Rationale:** `google-api-python-client` is synchronous and heavyweight. `httpx` is async-native, lightweight, and gives full control over headers (for ETag/If-Match). The Drive API v3 REST endpoints are well-documented and stable.

**Alternative considered:** `google-api-python-client` — synchronous, would require `run_in_executor` wrapping, and its auth layer conflicts with our stateless Bearer token approach.

### 5. ETag-based optimistic concurrency

**Choice:** Return the Google Drive file `etag` (from `files.get` response headers) on every read. Accept an optional `etag` parameter on writes — if provided, send `If-Match` header to the Drive API. On mismatch, return a clear conflict error with the current ETag.

**Rationale:** This matches how Google Drive natively handles concurrency. The agent can choose whether to use conflict detection (pass etag) or force-overwrite (omit etag). The system prompt will instruct agents to use ETags by default.

### 6. Binary file handling

**Choice:** Detect file type by mime_type. Text files (text/*, application/json, application/xml, etc.) returned as UTF-8 strings. Binary files returned as base64-encoded strings with a `binary: true` flag and `mime_type` in the response.

**Rationale:** Agents primarily work with text files. Base64 for binary preserves content integrity through JSON serialization. The mime_type metadata lets agents decide how to handle the content.

## Risks / Trade-offs

**[Google Drive API rate limits]** Google enforces per-user and per-project rate limits on Drive API calls. Path resolution requires multiple API calls (one per folder level). **Mitigation:** Per-session path caching reduces redundant calls. Document rate limit behavior in README. Consider exponential backoff on 429 responses.

**[Path ambiguity]** Google Drive allows duplicate file names in the same folder. Path resolution could match multiple files. **Mitigation:** Return the most recently modified file when duplicates exist. Log a warning. Document this behavior.

**[Token expiry mid-session]** If a long-running agent session outlasts the access token TTL (typically 1 hour), API calls will fail with 401. **Mitigation:** Return a clear "token expired" error. The agent can report this as a failure. Future enhancement: the errand worker could provide a token refresh endpoint.

**[Large file transfers]** Reading/writing large files (>10MB) through MCP tool responses could be slow and memory-intensive. **Mitigation:** Document a recommended file size limit. Return an error for files exceeding a configurable threshold (default 25MB).

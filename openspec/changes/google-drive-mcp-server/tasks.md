## 1. Project Setup

- [ ] 1.1 Initialize Python project with pyproject.toml, requirements.txt (fastmcp, httpx, uvicorn)
- [ ] 1.2 Create Dockerfile (Python base, install deps, EXPOSE 8080, CMD)
- [ ] 1.3 Create .github/workflows/build.yml (build + push image to ghcr.io/devops-consultants/google-drive-mcp-server)
- [ ] 1.4 Create docker-compose.yml for local development/testing

## 2. Server Transport and Auth

- [ ] 2.1 Create main server entry point with FastMCP in Streamable HTTP mode on configurable PORT (default 8080)
- [ ] 2.2 Implement Bearer token extraction from Authorization header on session init
- [ ] 2.3 Implement /health endpoint returning {"status": "ok"}
- [ ] 2.4 Add error handling for missing/invalid Authorization header
- [ ] 2.5 Write tests for session auth and health endpoint

## 3. Google Drive API Client

- [ ] 3.1 Create async Drive API client class using httpx (accepts Bearer token per-request)
- [ ] 3.2 Implement path-to-ID resolution by walking folder tree via files.list with parent filter
- [ ] 3.3 Add per-session path cache for resolved path-to-ID mappings
- [ ] 3.4 Implement handling for "My Drive" root and "Shared drives" roots
- [ ] 3.5 Add error mapping: 404 → not_found, 403 → permission_denied, 401 → auth_expired, 429 → rate_limited
- [ ] 3.6 Add retry with exponential backoff for 429 responses
- [ ] 3.7 Write tests for path resolution (mocked API responses)

## 4. File Operation Tools

- [ ] 4.1 Implement list_files tool (resolve path, list children, return structured entries)
- [ ] 4.2 Implement read_file tool (resolve path, download content, detect text/binary, return with etag)
- [ ] 4.3 Implement write_file tool (resolve parent path, upload content, handle If-Match etag, create intermediate folders)
- [ ] 4.4 Implement delete_file tool (resolve path, delete permanently)
- [ ] 4.5 Implement file_info tool (resolve path, return metadata without content)
- [ ] 4.6 Implement create_folder tool (resolve parent, create folder, handle intermediates)
- [ ] 4.7 Implement move_file tool (resolve source/dest, PATCH to move/rename)
- [ ] 4.8 Add file size limit check in read_file (configurable, default 25MB)
- [ ] 4.9 Write tests for all seven tools (mocked API responses, including error cases and ETag conflicts)

## 5. Documentation

- [ ] 5.1 Write README with project overview, deployment instructions, environment variables, tool reference
- [ ] 5.2 Document the path resolution behavior (root paths, shared drives, duplicate file handling)
- [ ] 5.3 Add CONTRIBUTING.md with development setup instructions

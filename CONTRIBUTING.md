# Contributing

## Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/devops-consultants/google-drive-mcp-server.git
   cd google-drive-mcp-server
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   pip install pytest pytest-asyncio respx
   ```

3. **Run the server locally:**

   ```bash
   python -m google_drive_mcp_server
   ```

   The server starts on `http://localhost:8080` by default. Set `PORT` to change:

   ```bash
   PORT=9090 python -m google_drive_mcp_server
   ```

4. **Run tests:**

   ```bash
   pytest                                    # all tests
   pytest tests/test_drive_client.py         # single file
   pytest tests/test_drive_client.py::TestPathResolution::test_resolve_root  # single test
   pytest -v                                 # verbose output
   ```

## Project Structure

```
google_drive_mcp_server/
├── __init__.py          # Package init
├── __main__.py          # Entry point for python -m
├── server.py            # FastMCP server, tools, auth middleware
└── drive_client.py      # Async Google Drive API client
tests/
├── conftest.py          # Shared fixtures
├── test_auth.py         # Bearer token extraction tests
├── test_health.py       # Health endpoint tests
├── test_drive_client.py # Drive client unit tests, path resolution
└── test_file_operations.py  # File operation integration tests
```

## Key Design Decisions

- **httpx** for async HTTP calls to Google Drive API v3 (not `google-api-python-client`)
- **Path-based interface** — agents use paths, server resolves to Google Drive file IDs
- **Per-session path cache** — resolved path→ID mappings cached within a session
- **respx** for mocking HTTP requests in tests
- **FastMCP middleware** for Bearer token extraction on session init

## Running with Docker

```bash
docker compose up          # local dev
docker build -t google-drive-mcp-server .
```

## Coding Conventions

- Python 3.11+
- Type hints on all public functions
- Async/await throughout
- Tests use `@pytest.mark.asyncio` and `@respx.mock` for HTTP mocking
- Error types follow the structured `DriveAPIError` pattern

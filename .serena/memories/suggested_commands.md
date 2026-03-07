# Suggested Commands

## Install & Run
```bash
# Install all dependencies (runtime + test)
pip install -e ".[dev]"

# Run server locally (default port 8080)
python -m google_drive_mcp_server

# Run with custom port
PORT=9090 python -m google_drive_mcp_server
```

## Testing
```bash
# Run all tests (verbose)
pytest tests/ -v

# Single test file
pytest tests/test_drive_client.py -v

# Single test class
pytest tests/test_drive_client.py::TestPathResolution -v

# Single test
pytest tests/test_drive_client.py::TestPathResolution::test_resolve_root -v
```

## Docker
```bash
# Local dev with docker compose
docker compose up

# Build image
docker build -t google-drive-mcp-server .

# Pull published image
docker pull ghcr.io/devops-consultants/google-drive-mcp-server:latest
```

## System Utils (macOS/Darwin)
```bash
git status / git diff / git log --oneline
python3.12 -m venv .venv && source .venv/bin/activate
```

## Notes
- System Python on macOS is 3.9 (too old). Use python3.12+ from homebrew.
- No linter/formatter configured in pyproject.toml currently.
- CI runs `pip install -e ".[dev]"` then `pytest tests/ -v`.

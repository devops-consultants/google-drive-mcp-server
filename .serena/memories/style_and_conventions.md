# Code Style and Conventions

## Language & Version
- Python 3.12+ (set in `pyproject.toml` requires-python and Dockerfile)

## Naming
- snake_case for functions, methods, variables
- PascalCase for classes (DriveClient, PathCache, DriveAPIError, BearerTokenMiddleware)
- UPPER_CASE for constants (DRIVE_API_BASE, FOLDER_MIME_TYPE, TEXT_MIME_EXACT)
- Private functions/methods prefixed with underscore (_map_error, _resolve_path, _request)

## Type Hints
- Type hints on all public function signatures
- Use `str | None` union syntax (not Optional)
- Use `dict[str, Any]` and `list[...]` (lowercase, not Dict/List)

## Async
- All I/O operations are async/await
- httpx.AsyncClient for HTTP calls
- Tests use `@pytest.mark.asyncio` (auto mode in pyproject.toml)

## Error Handling
- DriveAPIError is the structured error type with `.error`, `.message`, `.status_code`, `.etag`
- `_map_error()` maps HTTP status codes to DriveAPIError instances
- Tools catch DriveAPIError and return `.to_dict()` as error responses

## Testing Patterns
- `@respx.mock` decorator for mocking httpx HTTP calls
- Side effects via `respx.get(url__startswith=...).mock(side_effect=func)`
- Helper functions `_folder_entry()`, `_file_entry()` for building mock Drive API responses
- Each test creates its own DriveClient and closes it in a finally block

## Docstrings
- Simple one-line docstrings on public functions
- No docstrings required on test methods (descriptive test names suffice)
- No docstrings on private helper functions unless complex

## Imports
- Standard library first, then third-party, then local
- No unused imports (enforced by PR review)

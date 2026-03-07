## Requirements

### Requirement: Streamable HTTP transport

The server SHALL expose an MCP endpoint at `/mcp` using the Streamable HTTP transport protocol. It SHALL accept POST requests with JSON-RPC MCP messages.

#### Scenario: MCP client connects
- **WHEN** an MCP client sends a POST request to `/mcp` with a valid MCP initialize message
- **THEN** server responds with MCP capabilities including the list of available tools

#### Scenario: Non-MCP request to /mcp
- **WHEN** a non-MCP HTTP request is sent to `/mcp`
- **THEN** server returns an appropriate HTTP error response

### Requirement: Bearer token authentication

The server SHALL extract the OAuth access token from the `Authorization: Bearer <token>` header on MCP session initialization. All Google Drive API calls within that session SHALL use this token.

The server SHALL NOT store tokens beyond the session lifetime.

#### Scenario: Valid Bearer token
- **WHEN** an MCP client connects with a valid `Authorization: Bearer <token>` header
- **THEN** server accepts the session and uses the token for all Drive API calls

#### Scenario: Missing Authorization header
- **WHEN** an MCP client connects without an Authorization header
- **THEN** server rejects the session with an authentication error

#### Scenario: Expired token during session
- **WHEN** a Drive API call returns HTTP 401 (token expired)
- **THEN** server returns a tool error with `"error": "auth_expired"` and a message indicating the token has expired

### Requirement: Multi-session concurrent access

The server SHALL support multiple simultaneous MCP sessions, each with its own Bearer token. Sessions SHALL be fully isolated — no shared state between sessions.

#### Scenario: Two agents connect simultaneously
- **WHEN** Agent A connects with token_A and Agent B connects with token_B
- **THEN** Agent A's operations use token_A and Agent B's operations use token_B, with no cross-contamination

### Requirement: Health check endpoint

The server SHALL expose a `GET /health` endpoint that returns HTTP 200 with `{"status": "ok"}` when the server is running and ready to accept connections.

#### Scenario: Server is healthy
- **WHEN** a client sends `GET /health`
- **THEN** server returns HTTP 200 with `{"status": "ok"}`

### Requirement: Configurable port

The server SHALL accept a `PORT` environment variable (default `8080`) to configure the listening port.

#### Scenario: Custom port
- **WHEN** server starts with `PORT=9090`
- **THEN** server listens on port 9090

#### Scenario: Default port
- **WHEN** server starts without a PORT environment variable
- **THEN** server listens on port 8080

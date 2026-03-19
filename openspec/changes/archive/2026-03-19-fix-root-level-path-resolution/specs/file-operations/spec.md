## MODIFIED Requirements

### Requirement: Write file content

The server SHALL provide a `write_file` tool that accepts `path`, `content`, and optional `etag` parameters. It SHALL create or update the file and return `path`, `etag` (new), and `size`.

The tool description SHALL include a warning that parent folders are auto-created if they don't exist, and that Google Drive allows duplicate folder names — so writing to a path when resolution fails may create a duplicate folder. The description SHALL recommend verifying paths with `read_file` or `list_files` before writing to paths that should already exist.

When `etag` is provided, the server SHALL send an `If-Match` header to the Google Drive API. If the file has been modified since the provided ETag, the server SHALL return a conflict error instead of overwriting.

When `etag` is omitted, the server SHALL overwrite the file without conflict checking.

When auto-creating parent folders (because the parent path does not exist), the server SHALL log a warning message including the parent path being created.

#### Scenario: Create a new file
- **WHEN** agent calls `write_file(path="/Documents/new-report.md", content="# Report\n...")`
- **THEN** server creates the file (and any intermediate folders) and returns the new path, etag, and size

#### Scenario: Update with valid ETag
- **WHEN** agent calls `write_file(path="/Documents/report.md", content="updated", etag="abc123")`
- **AND** the file's current ETag matches `"abc123"`
- **THEN** server updates the file and returns the new etag

#### Scenario: Update with stale ETag (conflict)
- **WHEN** agent calls `write_file(path="/Documents/report.md", content="updated", etag="old-etag")`
- **AND** the file's current ETag does not match `"old-etag"`
- **THEN** server returns an error with `"error": "conflict"` and includes the current etag in the error response

#### Scenario: Update without ETag (force overwrite)
- **WHEN** agent calls `write_file(path="/Documents/report.md", content="updated")` without an etag parameter
- **THEN** server overwrites the file regardless of its current version

#### Scenario: Auto-create parent folder logs warning
- **WHEN** agent calls `write_file(path="/NewFolder/file.md", content="...")`
- **AND** `/NewFolder` does not exist
- **THEN** server creates the folder, logs a warning "Auto-creating parent folder: /NewFolder", and creates the file

## ADDED Requirements

### Requirement: Path resolution includes Shared Drive support unconditionally

The `_resolve_child()` method SHALL always include `supportsAllDrives=true` and `includeItemsFromAllDrives=true` API parameters in Google Drive file list queries, regardless of whether `parent_id` is `"root"` or any other folder ID. This ensures root-level folder lookups find folders in Shared Drives and folders accessible via domain-wide delegation.

#### Scenario: Root-level folder resolution includes Shared Drives
- **WHEN** path resolution looks up a folder name at the root level (parent_id is "root")
- **THEN** the Google Drive API request includes `supportsAllDrives=true` and `includeItemsFromAllDrives=true`

#### Scenario: Non-root folder resolution includes Shared Drives
- **WHEN** path resolution looks up a child within a subfolder
- **THEN** the Google Drive API request includes `supportsAllDrives=true` and `includeItemsFromAllDrives=true`

#### Scenario: Root-level folder found in Shared Drive
- **WHEN** agent calls `read_file(path="/SocialMedia/TweetsForApproval.md")`
- **AND** the `SocialMedia` folder exists (possibly in a Shared Drive context)
- **THEN** the path resolves successfully and the file content is returned

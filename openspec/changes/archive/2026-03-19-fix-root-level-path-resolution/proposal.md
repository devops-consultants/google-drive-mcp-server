## Why

Root-level folder lookups fail silently because `_resolve_child()` omits the `supportsAllDrives` and `includeItemsFromAllDrives` API parameters when `parent_id == "root"`. This causes `read_file` and other path-based operations to return "not found" for folders that exist. When `write_file` is subsequently called, it auto-creates a new folder (because `_ensure_folder` → `create_folder` DOES include `supportsAllDrives`), resulting in duplicate folders like "SocialMedia (1)" in Google Drive.

Discovered via production incident: a task-runner agent tried to read `/SocialMedia/TweetsForApproval.md`, got "not found", then wrote to the same path — which created a duplicate `SocialMedia` folder instead of updating the existing file.

## What Changes

- **Fix `_resolve_child()` API params**: Always include `supportsAllDrives=true` and `includeItemsFromAllDrives=true` regardless of `parent_id` value
- **Improve `write_file` tool description**: Add warnings about auto-folder-creation behavior and duplicate folder risk
- **Defensive write_file behavior**: Add optional `create_parents` parameter (default `true` for backwards compat) and log a warning when auto-creating parent folders

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `file-operations`: Fix path resolution for root-level lookups, improve write_file tool description and defensive behavior

## Impact

- **google_drive_mcp_server/drive_client.py**: Fix `_resolve_child()` params, add `create_parents` param to `write_file`
- **google_drive_mcp_server/server.py**: Update `write_file` tool description
- **tests/**: Add test for root-level folder resolution with `supportsAllDrives`

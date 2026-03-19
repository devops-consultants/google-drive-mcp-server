## Context

The Google Drive API requires `supportsAllDrives=true` and `includeItemsFromAllDrives=true` parameters to return results that include files from Shared Drives. The `_resolve_child()` method conditionally includes these parameters only when `parent_id != "root"`, meaning root-level folder lookups silently exclude Shared Drive content.

This creates an asymmetry: `_resolve_child()` can't find folders, but `create_folder()` always sends `supportsAllDrives=true`, so it creates new folders successfully — resulting in duplicates.

## Goals / Non-Goals

**Goals:**
- Fix root-level path resolution to always include Shared Drive parameters
- Add guardrails against accidental duplicate folder creation
- Improve tool descriptions to help agents avoid this class of error

**Non-Goals:**
- Changing the path resolution caching strategy
- Adding a separate "append" tool (out of scope)
- Changing the default `create_parents` behavior (backwards compat)

## Decisions

### 1. Always send `supportsAllDrives` in `_resolve_child()`

Remove the `if parent_id != "root"` conditional. These parameters are safe to include unconditionally — they're no-ops when no Shared Drives exist.

### 2. Improve `write_file` tool description

Add explicit warnings about auto-folder-creation and duplicate folder risk. Agent-facing tool descriptions are the primary way to guide LLM behavior.

### 3. Log warning on auto-folder-creation

When `write_file` creates parent folders via `_ensure_folder()`, emit a log warning. This aids debugging without changing behavior.

## Risks / Trade-offs

- **[Minimal risk]** Adding `supportsAllDrives` to root-level queries may return additional results from Shared Drives that were previously invisible → This is the correct behavior; hiding Shared Drive content was the bug.

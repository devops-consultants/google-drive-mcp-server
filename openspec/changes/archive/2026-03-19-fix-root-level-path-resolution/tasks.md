## 1. Fix Path Resolution Bug

- [x] 1.1 Remove the `if parent_id != "root"` conditional in `_resolve_child()` — always include `supportsAllDrives=true` and `includeItemsFromAllDrives=true` in API params
- [x] 1.2 Verify `list_files()` also includes these params unconditionally (check for same pattern)

## 2. Improve Tool Description

- [x] 2.1 Update `write_file` tool description in `server.py` to warn about auto-folder-creation, duplicate folder risk, and recommend verifying paths before writing

## 3. Defensive Logging

- [x] 3.1 Add warning log in `_ensure_folder()` when creating a folder that didn't previously exist (to aid debugging duplicate folder incidents)

## 4. Testing

- [x] 4.1 Add test: `_resolve_child()` sends `supportsAllDrives=true` when `parent_id == "root"`
- [x] 4.2 Add test: `_resolve_child()` sends `supportsAllDrives=true` when `parent_id` is a folder ID
- [x] 4.3 Add test: `write_file` to existing path resolves and updates (no duplicate folder created)
- [x] 4.4 Add test: `write_file` to non-existent path auto-creates parent and logs warning

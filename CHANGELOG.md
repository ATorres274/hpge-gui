## Changelog

### 2025-2026
- Migrated feature registry to features directory.
- Refactored browser tab to use module registry and RootFileManager.
- Merged file opener/browser modules.
- Removed feature registration from browser tab.
- Updated documentation to reflect modular architecture.

#### 2026-02-19
- Moved browser file-management into `modules/root_file_manager.py`.
- Added `features/root_directory.py` for directory population and details rendering.
- Moved `AdvancedSaveDialog` and export UI helpers into `modules/save_manager.py`.
- Updated packaging `pyHPGeGui.egg-info/SOURCES.txt` to include moved files.

#### 2026-02-20
- Consolidated peak finder helpers into `features/peak_search_feature.py` and added `modules/peak_manager.py` as the UI adapter (renamed from previous `peak_finder_module` layout). Updated histogram tab imports to use the new module.

**Phase 4: ErrorDispatcher Implementation (Comprehensive Error Handling)**:
- Created `modules/error_dispatcher.py` - singleton error management system
- Implemented ErrorLevel enum: INFO, WARNING, ERROR, CRITICAL
- Added ErrorEvent dataclass with full context preservation and serialization
- Integrated Python logging with stderr output and structured logging
- Implemented error history tracking (bounded to 100 events for memory efficiency)
- Created safe_execute wrapper for error wrapping and exception chaining
- Refactored 63+ bare except blocks across 5 core modules:
  - `gui_base/app_shell.py`: 15 blocks → ErrorDispatcher with ERROR/CRITICAL subscription for UI display
  - `modules/session_manager.py`: 15 blocks → ErrorDispatcher with proper context preservation
  - `modules/fit_module.py`: 15 blocks → ErrorDispatcher + added missing `_get_root_module()` method
  - `tab_managers/histogram_tab.py`: 8 blocks → ErrorDispatcher with hierarchical error routing
  - `tab_managers/browser_tab.py`: 10 blocks → ErrorDispatcher with context-specific routing
- Updated all refactored exception handlers with appropriate error levels based on severity
- Preserved fallback logic in critical paths (e.g., registry → direct import)
- Validated all syntax - zero errors across all refactored modules
- Updated ARCHITECTURE_REVIEW.md with comprehensive ErrorDispatcher documentation

### 2024-2025
- Initial implementation and architecture notes.
- Early feature registration and tab management patterns.

### See AGENT_CONTEXT.md, IMPLEMENTATION_SUMMARY.md, USER_GUIDE.md for current architecture and usage.

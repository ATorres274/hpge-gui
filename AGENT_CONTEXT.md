## Project Architecture (2026)

### Modular Design Overview
The project now follows a modular architecture:
- **Tabs** (e.g., browser, histogram, batch) are lightweight UI managers.
- **Modules** handle business logic and file operations (e.g., RootFileManager).
- **Features** are invoked by modules as needed, not directly registered in tabs.
- **Module Registry** pattern is used in tab managers to delegate operations.

### Browser Tab
- Uses a `ModuleRegistry` to manage modules (e.g., file_manager).
- Delegates file opening, browsing, and session management to `RootFileManager`.
- No longer registers features directly; features are handled by modules or elsewhere.

### Recent Changes (2026-02-19)
- File-management logic moved into `modules/root_file_manager.py` so the browser tab stays UI-focused.
- Directory population and details rendering are now implemented in `features/root_directory.py` and invoked by the file manager.

### Peak finder refactor
- Peak finding helpers were consolidated into `features/peak_search_feature.py` (automatic + manual helpers).
- The UI-facing adapter lives at `modules/peak_manager.py` and exposes `PeakFinderModule` for the histogram tab.


### Codebase Organization
- `features/feature_registry.py`: Central registry for feature lifecycle events.
- `modules/root_file_manager.py`: Unified file dialog, opening, and browsing logic.
- `tab_managers/browser_tab.py`: Refactored to use module registry, delegates file operations, feature registration removed.

### Documentation
All architectural updates and refactor notes prior to 2026 are now in CHANGELOG.md.

### Extra Notes from User
Agent should not worry about testing, or deleting files. The user will do this when needed.
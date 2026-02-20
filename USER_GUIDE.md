## User Guide (2026)

### Opening ROOT Files
Use the browser tab's open file button to select ROOT files. The tab delegates file operations to the `RootFileManager` module.

### Browsing and Navigation
The tree view displays ROOT file contents. Double-click histograms to open them in the histogram manager.

### Session Persistence
The browser tab automatically saves the last opened files in a session file.

### Modular Architecture
- Tabs are UI managers.
- Modules handle file operations and business logic.
- Features are invoked by modules as needed.

### Notes for Users (2026-02-19)
- The browser tab now delegates all file-opening and directory browsing to `modules/root_file_manager.py`. If you notice behavior differences, this is due to the refactor that separates UI from file logic.
- Object details displayed in the details panel are provided by `features/root_directory.py` when objects are selected.

- Peak finder helpers are available from `features/peak_search_feature.py` (automatic/manual). The histogram UI uses `modules/peak_manager.py` (`PeakFinderModule`) to integrate peak detection and manual peaks.

### For previous features and architecture, see CHANGELOG.md.
- **Non-Destructive Fitting**: All fits operate on histogram clones, preserving originals

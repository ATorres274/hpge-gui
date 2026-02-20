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

#### 2026-02-20 (ErrorDispatcher)
- Consolidated peak finder helpers into `features/peak_search_feature.py` and added `modules/peak_manager.py` as the UI adapter.
- Created `modules/error_dispatcher.py` — singleton error management system with ErrorLevel enum (INFO/WARNING/ERROR/CRITICAL), error history, and structured logging.
- Refactored 63+ bare except blocks across 5 core modules to use ErrorDispatcher.

#### 2026-02-20 (Histogram tab)
- Fixed `on_histogram_closed` callback arity (was passing 2 args, interface expects 1).
- Replaced flat `pack(side=LEFT)` axis-control row with compact 6-row grid layout (Title on top).
- Switched range vars from `DoubleVar` to `StringVar` with `f"{val:.1f}"` format for consistent 1-decimal display.
- Fixed axis label key mismatch (`xlabel`→`xtitle`, `ylabel`→`ytitle`) so label entries apply to rendered histogram.
- Added proportional scroll speed: step = 1% of axis max per tick.
- Added log-scale scroll: multiplicative step (×10^0.05 ≈ 1.12 per tick) when Log X/Y is active.
- Hard-max clamping: scroll and entry snap to histogram's original max silently (no dialog).
- Added auto-render on every entry change via `trace_add("write", ...)` on all StringVars.
- Added Reset button, Show Markers checkbox, and Title entry to control panel.
- Extracted calculation logic into new `modules/histogram_controls_module.py`.
- Extracted peak-finder panel into `HistogramPreviewRenderer._build_peak_panel()`.
- Added peak finder panel: Peaks treeview, manual entry, Find Peaks / Clear buttons, auto-find 200 ms after open.
- Rewrote test suite: 65 UX-driven tests across 10 classes.

### 2024-2025
- Initial implementation and architecture notes.
- Early feature registration and tab management patterns.

### See AGENT_CONTEXT.md and USER_GUIDE.md for current architecture and usage.

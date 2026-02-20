## Project Architecture (2026)

### Modular Design Overview
The project follows a strict **Tab → Module → Feature** architecture:
- **Tabs** (`tab_managers/`) — lightweight UI managers; wires widgets to modules, handles app callbacks.
- **Modules** (`modules/`) — domain logic, file I/O, session state; no tkinter imports.
- **Features** (`features/`) — pure computation and action handlers; no UI or persistent state.

### Key Tab: HistogramTab (`tab_managers/histogram_tab.py`)
Manages multiple open histogram previews. Delegates all rendering and controls to
`HistogramPreviewRenderer` (inner class in the same file). Exposes three callbacks to the app:
- `on_histogram_selected(key: str)` — user selected a histogram
- `on_histogram_closed(remaining_count: int)` — histogram closed
- `on_histogram_opened(list[(key, name)])` — histogram opened

### HistogramPreviewRenderer
Builds the per-histogram UI panel:
- **Control grid** (top, compact, 6 rows):
  - Row 0: Title entry
  - Row 1: X: [xmin] to [xmax] Log X
  - Row 2: X label entry
  - Row 3: Y: [ymin] to [ymax] Log Y
  - Row 4: Y label entry
  - Row 5: Show Markers checkbox + Reset button
- **Peak finder panel** (right): Peaks treeview, manual entry, Find/Clear buttons
- **Preview label** (bottom): receives Tk PhotoImage from `HistogramRenderer`

Peak panel construction is extracted into `_build_peak_panel(middle_bar, app, obj)`.

### HistogramControlsModule (`modules/histogram_controls_module.py`)
Stateless calculation module (no tkinter). Called by `HistogramPreviewRenderer`:
- `compute_defaults(obj)` — extracts axis limits, scroll steps, labels, title from histogram
- `clamp_min/clamp_max(current, step, direction_down, ..., log_mode=False)` — scroll arithmetic;
  multiplicative (×10^0.05 per tick) when `log_mode=True`, additive otherwise
- `validate_min/validate_max(raw, other_raw, hard_limit=None)` — focus-out validation;
  silently snaps to hard limit (histogram max) if exceeded
- `build_render_options(w, h, ...)` — assembles options dict for HistogramRenderer

### Browser Tab
- Uses a `ModuleRegistry` to manage modules (e.g., file_manager).
- Delegates file opening, browsing, and session management to `RootFileManager`.

### Peak Finder
- Domain logic in `features/peak_search_feature.py` (automatic + manual helpers).
- UI adapter: `modules/peak_manager.py` (`PeakFinderModule`).
- `HistogramPreviewRenderer` owns peak panel UI; `PeakFinderModule` owns peak data.

### Codebase Organization
- `features/feature_registry.py`: Central registry for feature lifecycle events.
- `modules/root_file_manager.py`: Unified file dialog, opening, and browsing logic.
- `modules/histogram_controls_module.py`: Pure axis-control calculations for histogram tab.
- `tab_managers/browser_tab.py`: Delegates file operations to module registry.
- `tab_managers/histogram_tab.py`: `HistogramTab` + `HistogramPreviewRenderer`.

### Documentation
All architectural updates prior to 2026-02 are in `CHANGELOG.md`.

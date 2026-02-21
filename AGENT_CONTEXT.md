## Project Architecture (2026)

### Modular Design Overview
The project follows a strict **Tab → Module → Feature** architecture:
- **Tabs** (`tab_managers/`) — lightweight UI managers; wires widgets to modules, handles app callbacks.
- **Modules** (`modules/`) — domain logic, file I/O, session state; no tkinter imports.
- **Features** (`features/`) — pure computation and action handlers; no UI or persistent state.

### Key Tab: HistogramTab (`tab_managers/histogram_tab.py`)
Manages multiple open histogram previews. Delegates per-histogram UI creation to
`HistogramPreviewRenderer` (in `tab_managers/histogram_preview_renderer.py`).
Exposes three callbacks to the app:
- `on_histogram_selected(key: str)` — user selected a histogram
- `on_histogram_closed(remaining_count: int)` — histogram closed
- `on_histogram_opened(list[(key, name)])` — histogram opened

`HistogramPreviewRenderer` is re-exported from `histogram_tab.py` so existing
imports of the form ``from tab_managers.histogram_tab import HistogramPreviewRenderer``
continue to work.

### HistogramPreviewRenderer (`tab_managers/histogram_preview_renderer.py`)
Builds the per-histogram UI panel:
- **Control grid** (top, compact, 6 rows):
  - Row 0: Title entry
  - Row 1: X: [xmin] to [xmax] Log X
  - Row 2: X label entry
  - Row 3: Y: [ymin] to [ymax] Log Y
  - Row 4: Y label entry
  - Row 5: Show Markers checkbox + Reset button
- **Peak finder panel** (right of axis controls):
  - Treeview listing found peaks
  - Manual entry + Add button
  - Find Peaks / Clear / **Fit All** buttons
  - Peak search configuration (sigma, energy range, min counts) was **removed** — too unintuitive
- **Fit panel** (right of peak panel):
  - `Listbox` (height 4) listing fit names; replaces old Combobox
  - **+ Fit** and **Remove** buttons below the listbox
  - Active fit card shows: Func combobox, E (keV), W (keV), Fit button
  - Parameter grid uses **2-per-row layout** (``cols_per_row = 2``) for readability
  - Seed parameters pre-filled via `FitFeature.default_fit_params` when energy is known
- **Save row** (right-aligned, between controls and bottom separator):
  - Single **Save…** button; opens `_open_save_dialog`
- **Preview area** (bottom):
  - Left: main histogram `Label`
  - Right: `PanedWindow` (vertical, weight 3:1) containing:
    - Fit results `Text` widget with scrollbar (fills available space)
    - Fit preview `Label`

#### Save Dialog (`_open_save_dialog`)
Format checkboxes:
- PNG (preview) / PDF (preview) — image renders
- CSV (peaks) + optional "**+ fit results**" sub-checkbox — when fit results is checked,
  peaks checkbox is forced on and disabled; the output CSV includes both peaks and fits
- JSON (peaks) + "**+ fit results**" — same coupling logic
- PDF (fit report) — multi-page fit report (see below)

#### Fit Report PDF (`SaveManager.export_fit_report_pdf`)
Delegates to `FitExportFeature.export_report_pdf`. Page layout:
1. **Title page** — histogram name, generation date, fit summary list
2. **Overview page** — full unzoomed spectrum + all fit curves in distinct colours;
   `TLegend` with ``#chi^{2}/ndf`` value per fit
3. **One page per fit** — zoomed histogram + fit curve + `TPaveText` overlay of full results

### HistogramControlsModule (`modules/histogram_controls_module.py`)
Stateless calculation module (no tkinter). Called by `HistogramPreviewRenderer`:
- `compute_defaults(obj)` — extracts axis limits, scroll steps, labels, title from histogram
- `clamp_min/clamp_max(current, step, direction_down, ..., log_mode=False)` — scroll arithmetic;
  multiplicative (×10^0.05 per tick) when `log_mode=True`, additive otherwise
- `validate_min/validate_max(raw, other_raw, hard_limit=None)` — focus-out validation;
  silently snaps to hard limit (histogram max) if exceeded
- `build_render_options(w, h, *, ..., peak_energies, manual_peak_energies)` — assembles options
  dict for HistogramRenderer; `peak_energies` → automatic peaks (red star, style 29);
  `manual_peak_energies` → manual peaks (blue open circle, style 24)
- `detect_scroll_direction(event) -> bool` — returns True for downward scroll

### Browser Tab
- Uses a `ModuleRegistry` to manage modules (e.g., file_manager).
- Delegates file opening, browsing, and session management to `RootFileManager`.

### Peak Finder
- Domain logic in `features/peak_search_feature.py` (automatic + manual helpers).
- UI adapter: `modules/peak_manager.py` (`PeakFinderModule`) — no tkinter imports;
  accepts widget references typed as `Any` and detects Treeview via duck-typing.
- `HistogramPreviewRenderer` owns peak panel UI; `PeakFinderModule` owns peak data.
- Each peak dict carries a ``"source"`` key: ``"automatic"`` or ``"manual"``.
  The renderer passes separate lists to `build_render_options` so they render differently.

### Save Architecture
`SaveManager` (`modules/save_manager.py`) is a **thin coordinator** — it owns the
public API used by tab managers and delegates all I/O work to three feature instances:

| Feature | Responsibility |
|---|---|
| `features.renderer_feature.RendererFeature` | PNG / PDF preview renders |
| `features.peak_export_feature.PeakExportFeature` | Peak CSV / JSON serialisation |
| `features.fit_export_feature.FitExportFeature` | Fit CSV / JSON + multi-page PDF report |

`PeakExportFeature` also exposes the module-level helper `_fit_state_val` (used by
`FitExportFeature`) that extracts plain Python values from fit-state dicts which may
carry either native values or legacy tkinter `StringVar` objects.

`FitExportFeature` owns `_FIT_COLORS` (module-level constant: distinct ROOT colour
indices) and all ROOT canvas / TPaveText / TLegend drawing helpers for the PDF report.

### Codebase Organization
- `features/feature_registry.py`: Central registry for feature lifecycle events.
- `features/peak_export_feature.py`: Peak CSV/JSON export; `_fit_state_val` helper.
- `features/fit_export_feature.py`: Fit CSV/JSON export + multi-page PDF fit report.
- `modules/root_file_manager.py`: Unified file dialog, opening, and browsing logic.
- `modules/histogram_controls_module.py`: Pure axis-control calculations for histogram tab.
- `modules/save_manager.py`: Thin coordinator; delegates to feature layer.
- `tab_managers/browser_tab.py`: Delegates file operations to module registry.
- `tab_managers/histogram_tab.py`: `HistogramTab` — manages multiple open histograms;
  re-exports `HistogramPreviewRenderer` for backward compatibility.
- `tab_managers/histogram_preview_renderer.py`: `HistogramPreviewRenderer` — per-histogram
  UI panel; delegates computation to `HistogramControlsModule`, peak data to
  `PeakFinderModule`, and fitting to `FitModule`.

### Documentation
All architectural updates prior to 2026-02 are in `CHANGELOG.md`.

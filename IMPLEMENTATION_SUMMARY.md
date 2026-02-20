## Implementation Summary (2026)

### Recent Refactor (2026-02-19)
- **Moved file-management logic** from the browser tab into `modules/root_file_manager.py` so the tab focuses on UI only.
- **Added feature helper** `features/root_directory.py` to populate directory nodes and render object details on demand.
- **Relocated save/export UI**: `AdvancedSaveDialog` and export helpers moved into `modules/save_manager.py`.
- **Updated packaging metadata**: `pyHPGeGui.egg-info/SOURCES.txt` updated to include moved files and remove stale references.

### Modularization
- Tabs are UI managers; modules handle business logic.
- Browser tab uses `ModuleRegistry` and `RootFileManager`.
- Features are invoked by modules, not registered in tabs.

### Refactoring
- Moved feature registry to features directory.
- Merged file opener/browser modules into `RootFileManager`.
- Updated imports and file names for consistency.
- Removed feature registration from browser tab.

### Session Management
- Browser tab saves session file with last opened ROOT files.

### See CHANGELOG.md for previous updates.
  - Bound to object selection and tab change events
- **FeatureRegistry**:
  - Manages feature instantiation and lifecycle
  - Binds features to events
  - Tracks which features are active on which tabs

### tab_managers/ - Tab Implementations (Feature Logic)

**browser_tab.py** - ROOT file browser and navigation
- **BrowserTabManager** - manages file browser UI and logic
- **Responsibilities**: Tree view, file opening, directory navigation, object selection
- **UI Components**:
  - Tree view with color-coded ROOT object types
  - Color scheme: TH1*=blue (bold), TGraph*=green (bold), TTree*=purple, TF*=red, directories=orange (bold), other=gray
  - Details panel for object metadata
  - Double-click to open histograms
- **Key Methods**:
  - `build_ui(parent)` - constructs tree view and detail panel
  - `open_path(path)` - opens ROOT file and populates tree
  - `on_double_click()` - handles histogram opening
  - `_populate_directory()` - populates tree with directory contents
  - `_get_tag_for_class()` - maps ROOT classes to color tags
- **Data Management**:
  - `_open_root_files: dict` - tracks open ROOT files
  - `_root_paths_by_node: dict` - maps tree nodes to file paths

**histogram_tab.py** - Histogram rendering with interactive controls
- **HistogramTabController.build_histogram_tab()** builds complete histogram UI
- **Rendering Options Panel**:
  - Axis ranges: X min/max, Y min/max (empty means auto-scale)
  - Scale controls: Log X, Log Y checkboxes
  - Title customization: main histogram title, X-axis title, Y-axis title
  - Marker display: toggle for manual peak visualization
- **Peak Finder Panel** (if peak_finder provided):
  - Two side-by-side text areas: "Peaks Found" (auto-detected) and "User Peaks" (manual)
  - Buttons: "Find Peaks", "Clear", "Auto Fit"
  - Manual peak entry: text field for energy in keV, Enter key adds peak
- **Rendering Pipeline**:
  - All control changes call `schedule_render()` which debounces rendering at 150 ms
  - Rendering happens asynchronously via `RootRenderer.render_into_label_async()`
  - All options collected in dict via `build_options()` which validates numeric inputs
- **Key Methods**:
  - `reset_to_defaults()` - resets all controls to histogram's original state
  - `build_options() -> dict | None` - creates rendering options dict with validation
  - `parse_float(value: str, field_name: str) -> float | None` - validates numeric input
  - `save()` - opens AdvancedSaveDialog with render_options dict
  - `open_canvas()` - opens ROOT TCanvas for histogram (future enhancement)
- **Rendering Options Dict Structure**:
  ```python
  {
    "logx": bool,                    # Log scale on X axis
    "logy": bool,                    # Log scale on Y axis
    "show_markers": bool,            # Show peak markers
    "title": str,                    # Main histogram title
    "xtitle": str,                   # X-axis label
    "ytitle": str,                   # Y-axis label
    "markers": list[float],          # Energies for vertical marker lines
    "xmin": float | None,            # X-axis minimum (None=auto)
    "xmax": float | None,            # X-axis maximum (None=auto)
    "ymin": float | None,            # Y-axis minimum (None=auto)
    "ymax": float | None,            # Y-axis maximum (None=auto)
  }
  ```
- **Debounce Strategy**: When user edits controls, rendering is scheduled at 150 ms interval (prevents excessive re-renders while dragging slider, typing in field, etc.)

**modules/fit_module.py** - Fitting interface with dropdown-based fit selection (moved from `tab_managers/fitting_tab.py`)
- **FittingFeature** - manages all fit operations and state
- **Architecture Update (Feb 2026)**: Converted from notebook-based (tab-based switching) to dropdown-based system with frame visibility toggling
- **Instance Variables**:
  - `fit_count: int` - incremental counter for naming new fits (1, 2, 3, ...)
  - `fit_states: dict[int, dict]` - central storage for all fit states, keyed by fit_id
  - `fit_frames: dict[int, ttk.Frame]` - UI frames for each fit, keyed by fit_id
  - `current_fit_id: int | None` - currently selected fit in dropdown (determines which frame is visible)
  - `fit_dropdown_var: tk.StringVar` - StringVar bound to dropdown widget
  - `fit_dropdown: ttk.Combobox` - dropdown widget (readonly, populated dynamically)
  - `fit_container: ttk.Frame` - parent container for fit frames
  - `current_hist_clone: TH1 | None` - histogram clone for non-destructive fitting
  - `_app: Tk` - reference to root app for scheduling callbacks
  - `_renderer: RootRenderer` - centralized rendering engine
  - `_export_manager: ExportManager` - fit data export handler
  - `peak_finder: PeakFinderFeature | None` - reference to peak finder (for auto-fit integration)

- **Fit State Dictionary** (stored in `fit_states[fit_id]`):
  ```python
  {
    "fit_id": int,                           # Unique identifier for this fit
    "fit_func_var": tk.StringVar,            # Fit function: gaus, landau, expo, pol1, pol2, pol3
    "fit_options_var": tk.StringVar,         # ROOT fit options string, default "SQ"
    "energy_var": tk.StringVar,              # Center of fit range in keV
    "width_var": tk.StringVar,               # Width of fit range in keV
    "params_frame": ttk.LabelFrame,          # Container for parameter entry widgets
    "param_entries": list[ttk.Entry],        # Initial parameter value entries (dynamic count)
    "param_fixed_vars": list[tk.BooleanVar], # Fix parameter checkboxes (one per parameter)
    "left_frame": ttk.Frame,                 # Left side frame for preview image
    "right_frame": ttk.Frame,                # Right side frame for results text
    "image_label": ttk.Label,                # Displays preview image (PhotoImage)
    "image_ref": PhotoImage | None,          # Holds PhotoImage reference (prevents GC)
    "fit_result": TFitResult | None,         # Temporary ROOT fit object (cleared after cache)
    "cached_results": dict,                  # Cached fit results as native Python types
    "fit_result_text": tk.Text,              # Text widget displaying formatted results
    "refit_pending": {"id": int | None},     # Debounce timer ID for auto-refit on param change
    "peak_idx": int | None,                  # Original peak index from peak finder
    "has_fit": bool,                         # Whether fit has been executed
    "fit_epoch": int,                        # Epoch counter for cache invalidation
    "fit_func_obj": TF1 | None,              # ROOT TF1 function object for rendering
  }
  ```

- **Parameter Counts by Fit Function**:
  - Gaussian: 3 parameters (p0=constant, p1=mean, p2=sigma)
  - Landau: 2 parameters (p0=amplitude, p1=most probable value)
  - Exponential: 2 parameters (p0=amplitude, p1=decay constant)
  - Polynomial 1: 2 parameters (p0=constant, p1=linear coefficient)
  - Polynomial 2: 3 parameters (p0, p1, p2)
  - Polynomial 3: 4 parameters (p0, p1, p2, p3)

- **Key Methods**:
  - `_add_fit_tab(energy: float | None, width: float | None, peak_idx: int | None, auto_fit: bool) -> int`
    - Creates new fit entry in dropdown
    - Increments fit_count to generate unique fit_id
    - Creates UI via `_create_fit_ui()`
    - Stores fit_state in both `fit_states[fit_id]` and `fit_frames[fit_id]`
    - Updates dropdown: `fit_dropdown.config(values=[...current values... + new fit name...])`
    - Selects new fit: `fit_dropdown.set(fit_name)`
    - If `auto_fit=True`: schedules `_perform_fit_for_tab()` with 100 ms delay
    - Returns fit_id
  
  - `_create_fit_ui(tab_frame: ttk.Frame, energy, width, peak_idx, fit_id) -> dict`
    - Builds complete fit UI inside tab_frame
    - Creates control row: Fit Function (Combobox), Energy (Entry), Width (Entry), Fit Options (Entry), Fit (Button)
    - Creates parameters frame with dynamic entries based on fit function
    - Creates left/right split: left for preview image, right for results text
    - Binds Fit Function Combobox to `_on_fit_func_changed_for_tab()` to update parameter frame
    - Returns initialized fit_state dict
  
  - `_on_fit_dropdown_changed(event=None)`
    - Called when user selects different fit in dropdown
    - Gets selected fit_id from dropdown display text
    - Calls `_show_fit_frame(fit_id)` to update visibility
    - Schedules rendering if fit has results
  
  - `_show_fit_frame(fit_id: int)`
    - Hides all fit frames in `fit_frames` dict
    - Shows selected fit frame (makes it visible)
    - Updates rendering if fit has results (calls RootRenderer)
  
  - `_perform_fit_for_tab(app, fit_state: dict)`
    - Validates energy and width inputs (must be numeric, width > 0)
    - Calculates x-axis range: `[energy - width/2, energy + width/2]`
    - **Critical Step**: Calls `_render_fit_preview_for_tab()` to cache results BEFORE ROOT objects invalidate
    - Extracts ROOT TFitResult to native Python types via `_cache_fit_results()`
    - Sets `has_fit = True`
    - Calls `_display_fit_results_for_tab()` to show results in text widget
    - Uses debounce (`refit_pending`) to prevent excessive refits from parameter edits (500 ms delay)
  
  - `_cache_fit_results(fit_result: TFitResult, fit_state: dict)`
    - Extracts all data from temporary ROOT TFitResult object
    - Extracts: chi-square, NDF, reduced chi-square, parameters, parameter errors
    - **Gaussian-specific calculations**:
      - FWHM: `2.355 * sigma` (Full Width at Half Maximum)
      - Centroid: p1 (mean)
      - Area: `p0 * p2 * sqrt(2*pi)` (integral under curve)
    - **Landau-specific calculations**:
      - Most probable value: p1
      - Width: p2
    - Stores all in `fit_state["cached_results"]` dict
    - **Critical**: Clears `fit_state["fit_result"]` to avoid null-pointer invalidation in ROOT
    - Increments `fit_state["fit_epoch"]` for cache tracking
  
  - `_render_fit_preview_for_tab(fit_state: dict, xrange: tuple | None) -> PhotoImage`
    - Creates TCanvas in batch mode with 16:9 aspect ratio
    - Draws histogram (optionally cropped to xrange)
    - Overlays ROOT TF1 fit function curve for visualization
    - Converts to PNG image in memory (PIL Image)
    - Stores PhotoImage reference in `fit_state["image_ref"]` (prevents garbage collection)
    - Displays in label via `image_label.config(image=image_ref)`
  
  - `_display_fit_results_for_tab(fit_state: dict)`
    - Formats cached results into readable text
    - Displays: chi-square, NDF, reduced chi-square
    - For each parameter: name, value, error
    - For Gaussian: FWHM, centroid, area with units
    - For Landau: most probable value, width
    - Updates `fit_result_text` widget
    - Status: "Success" if fit executed, "Pending" otherwise
  
  - `_save_fit_for_tab(fit_state: dict)`
    - Opens AdvancedSaveDialog with current fit_state and all fit_states
    - Passes render_options for histogram rendering
    - User selects export formats (PNG, PDF, CSV, JSON)
  
  - `_export_all_csv()` and `_export_all_json()`
    - Delegates to ExportManager methods
    - Opens file save dialog
    - Exports all fits in fit_states dict
    - Returns list of saved filepaths

- **Fit Execution Pipeline**:
  1. User enters energy (keV), width (keV), selects fit function
  2. User enters initial parameter guesses in parameter frame
  3. User clicks "Fit" button
  4. `_perform_fit_for_tab()` executes ROOT fit
  5. `_render_fit_preview_for_tab()` generates preview BEFORE ROOT object invalidation
  6. `_cache_fit_results()` extracts all data to native Python types
  7. `_display_fit_results_for_tab()` shows results
  8. If user edits parameters: auto-refit scheduled with 500 ms debounce

**features/peak_search_feature.py** - Combined peak detection helpers (automatic + manual)
- **PeakSearchAutomatic / PeakSearchManual** - automatic and manual peak helpers (TSpectrum wrapper and manual-peak helper). The UI-level adapter is provided by `modules/peak_manager.py` which exposes `PeakFinderModule` and composes these helpers.
- **Instance Variables**:
  - `peaks: list[dict]` - detected peaks with structure: `{"energy": float, "counts": float | None, "source": "auto" | "manual"}`
  - `current_hist: TH1 | None` - reference to current histogram
  - `fitting_feature: FittingFeature | None` - reference to fitting tab (for creating fits)
  - `host_notebook: ttk.Notebook | None` - parent notebook (for tab switching)
  - `_peaks_text: tk.Text` - text widget for "Peaks Found" display
  - `_user_peaks_text: tk.Text` - text widget for "User Peaks" display
  - `_manual_peak_var: tk.StringVar` - manual peak entry field
  - `_render_callback: callable` - callback to trigger histogram re-render

- **Key Methods**:
  - `_find_peaks(app)`
    - Creates ROOT TSpectrum object
    - Calls TSpectrum.Search() with default sigma=3, threshold=0.1
    - Extracts peak energies and stores with bin counts
    - Updates "Peaks Found" text display
    - Triggers histogram render via `_render_callback()`
  
  - `_auto_fit_peaks()` - Create and auto-fit tabs for all detected peaks
    - **Feb 2026 Fix**: Updated from old `fit_tabs_notebook` reference to new dropdown system
    - Validates: returns if no peaks or fitting_feature is None
    - Clears existing fits:
      - `fit_states.clear()` - empties all fit state data
      - `fit_frames.clear()` - removes all UI frames
      - `fit_count = 0` - resets naming counter
    - Clears dropdown UI:
      - `fit_dropdown.config(values=[])` - removes all options
      - `fit_dropdown_var.set("")` - clears selection
      - `current_fit_id = None` - resets selection tracking
    - Calls `_create_fit_tabs_sequentially(0)` to create fits with delays
    - Switches UI to Fit tab: loops through notebook tabs looking for "Fit" in text
    - **Rationale**: Sequential creation with delays prevents race conditions from concurrent fit execution
  
  - `_create_fit_tabs_sequentially(index: int)` - Recursive fit creation with delays
    - Base case: if `index >= len(self.peaks)`: return
    - Recursive case:
      - Extracts peak energy and counts from `peaks[index]`
      - Calls `fitting_feature._add_fit_tab(energy=energy, width=10.0, peak_idx=None, auto_fit=True)`
      - Schedules next peak: `self.parent_app.after(200, lambda: _create_fit_tabs_sequentially(index+1))`
    - 200 ms delay between peaks prevents race conditions and CPU overload
  
  - `_add_manual_peak()`
    - Gets energy from `_manual_peak_var` text field
    - Validates numeric value with error dialog
    - Looks up bin content in current histogram
    - Appends to `peaks` list with source="manual"
    - Sorts peaks by energy
    - Updates "User Peaks" text display
    - Triggers histogram render

- **Peak Display Formats**:
  - "Peaks Found": Shows auto-detected peaks with energies and counts
  - "User Peaks": Shows manually added peaks with energies
  - Format: "1234.5 keV (12345 counts)" for auto, "1234.5 keV" for manual

### features/ - Feature Implementations & UI Dialogs

**feature.py** - Base Feature class
- Abstract class defining plugin interface
- Methods:
  - `build_ui(app: Tk, parent: Frame)` - Construct feature UI
  - `on_selection(obj, root_path: str, path: str)` - Handle object selection

**advanced_save.py** - Multi-format save dialog
- **AdvancedSaveDialog** - Unified save/export dialog for all formats
- **Constructor Parameters**:
  - `parent` - parent window
  - `root` - ROOT.gROOT reference for rendering
  - `obj` - histogram object
  - `default_name` - default filename (stem, no extension)
  - `peak_finder` - optional peak finder module reference
  - `subdirectory` - optional output subdirectory
  - `render_options` - optional dict with rendering settings
  - `fit_states` - optional dict of fit states
  
- **Export Format Checkboxes** (visibility based on availability):
  - PNG: Always available → `SaveManager.save_render_files(..., save_png=True, save_pdf=False)`
  - PDF: Always available → `SaveManager.save_render_files(..., save_png=False, save_pdf=True)`
  - CSV (Peaks): Available if `peak_finder is not None` → use `peak_finder.peaks` (tab-level export UI performs file writing)
  - CSV (Fit Results): Available if `fit_states is not empty` → `ExportManager.export_fit_results_csv(...)`
  - JSON (Fit Results): Available if `fit_states is not empty` → `ExportManager.export_fit_results_json(...)`
  
- **Key Method**:
  - `_save()` - Execute save/export for all checked formats
    - Creates output directory if needed
    - Calls appropriate SaveManager/ExportManager methods
    - Handles errors and shows completion message
    - Returns list of all saved filepaths

**export_ui.py** - UI dialog utilities
- Functions:
  - `ask_saveas(initial_dir, initial_file, filetypes) -> str` - File save dialog
  - `ask_openfile(initial_dir, filetypes) -> str` - File open dialog
  - `info(title, message)` - Info messagebox
  - `error(title, message)` - Error messagebox

### modules/ - Core Business Logic

**root_renderer.py** - Centralized ROOT rendering
- **RootRenderer** - wraps ROOT rendering with consistent settings
- **Settings**:
  - DPI: 150 (output resolution)
  - Aspect ratio: 16:9 (default)
  - Batch mode: True (SetBatch for macOS stability)
  - Output suppression: Redirects stdout/stderr
  
- **Key Methods**:
  - `render_to_file(root, obj, filepath, width, height, options)` - Render to PNG/PDF file
    - Creates TCanvas with specified dimensions
    - Draws histogram with rendering options
    - Saves to file (format from extension)
    - Returns filepath
  
  - `render_into_label_async(root, obj, label, options, delay_ms)` - Render into Tkinter label
    - Schedules async rendering with optional delay
    - Renders to PIL Image in memory
    - Converts to PhotoImage
    - Displays in Tkinter Label widget
    - Non-blocking UI updates
  
  - `render_to_image(root, obj, width, height, options)` - Return PIL Image
    - In-memory rendering without file I/O
    - Used for display and export

**save_manager.py** - Render file persistence (PNG, PDF)
- **SaveManager** class
- **Key Methods**:
  - `default_save(root, obj, directory, filename)` - Quick PNG+PDF save
    - Uses 1920x1080 (16:9) default dimensions
    - Saves to `{directory}/{filename}.png` and `.pdf`
    - Creates directory if needed
    - Returns list of saved filepaths
  
  - `save_render_files(root, obj, directory, filename, width, height, render_options, save_png, save_pdf)` - Flexible save
    - Saves PNG and/or PDF based on boolean flags
    - Uses provided render_options dict
    - Creates directory if needed
    - Returns list of saved filepaths

**export_manager.py** - Data export to CSV and JSON
- **ExportManager** class
- **CSV Format**:
  - Columns: Fit_ID, Fit_Function, Energy_keV, Width_keV, Chi2, NDF, Reduced_Chi2, Status, Parameters, Errors, FWHM_keV, Centroid_keV, Area
  - One row per fit
  - Parameters formatted as comma-separated list
  - Suitable for spreadsheet analysis
  
- **JSON Format**:
  - Nested structure with metadata (timestamp, histogram info)
  - Detailed fit parameters and errors
  - Fit-specific calculations (FWHM/centroid for Gaussian, MPV for Landau)
  
- **Key Methods**:
  - `export_fit_results_csv(fit_states, directory, filename)` - Export all fits to CSV
  - `export_fit_results_json(fit_states, directory, filename)` - Export all fits to JSON
  - `export_single_fit(fit_id, fit_state, directory, filename)` - Single fit export

**session_manager.py** - Workspace state persistence
- **SessionManager** class
- **Key Methods**:
  - `save_session(histogram_name, histogram_path, fit_states, peaks)` - Save workspace
    - Stores to JSON in `~/.pyhpge_gui/sessions/`
    - Includes all fit states and parameters
    - Includes detected and manual peaks
  
  - `load_session(session_path)` - Load workspace from file
    - Returns dict with all saved state
  
  - `auto_save_session(histogram_name, fit_states, peaks)` - Background auto-save
    - Silent save to `~/.pyhpge_gui/sessions/autosave/`
  
  - `load_auto_save(histogram_name)` - Restore from auto-save

**root_object_manager.py** - ROOT object lifecycle management
- Handles opening ROOT files
- Manages histogram clones for non-destructive fitting
- Cleanup and resource management

## Key Features & Workflows

### 1. Non-Destructive Fitting
- Histogram clone created on first fit: `obj.Clone(f"{obj.GetName()}_clone")`
- All fit operations use clone, original histogram rendering unaffected
- Clone reused for all subsequent fits (efficiency)
- Fallback to original if clone creation fails

### 2. Dropdown-Based Fit Selection (Feb 2026 Redesign)
- **Previous system**: Notebook with tabs for each fit (tab-based switching)
- **Current system**: Dropdown combobox with frame visibility toggling
  - Dropdown displays: "Fit 1 (1000 keV)", "Fit 2 (2000 keV)", etc.
  - Selecting dropdown triggers `_on_fit_dropdown_changed()`
  - Shows selected fit frame, hides all others (visibility toggling)
  - Frames stored in `fit_frames` dict for efficient visibility management
  - All fits remain in memory and can be accessed without rebuilding UI
  
- **Benefits**:
  - Cleaner, less cluttered UI
  - Better scaling for many fits (no tab scrolling needed)
  - More space allocated to preview image and results display
  - Easier to scan list of all fits at once
  - Faster switching between fits (no tab recreation)

### 3. Auto-Fit Peak Integration (Feb 2026 Update)
- **Auto Fit button** in histogram tab triggers `peak_finder._auto_fit_peaks()`
 - Located in: `features/peak_search_feature.py` and `modules/peak_manager.py` (integrated into histogram tab)
- Workflow:
  1. Validates peaks detected: `if not self.peaks: return`
  2. Clears existing fits: `fit_states.clear()`, `fit_frames.clear()`, reset `fit_count`
  3. Clears dropdown UI: `fit_dropdown.config(values=[])`, `fit_dropdown_var.set("")`, reset `current_fit_id`
  4. Creates fit tabs sequentially with 200 ms delays (prevents race conditions)
  5. Each peak gets 10 keV fixed width fit
  6. Auto-fit flag triggers immediate fit execution (scheduled with 100 ms delay)
  7. Switches UI to Fit tab to show results

- **Previous Issue (Fixed Feb 2026)**:
  - Code referenced old `fit_tabs_notebook` (notebook-based system)
  - Tried to `.forget()` tabs (not applicable to dropdown)
  - Attempted to check `if self.fitting_feature.fit_tabs_notebook:` (no longer exists)
  - **Fix**: Updated to clear `fit_frames` dict and dropdown values instead

### 4. Rendering Pipeline
- All rendering goes through `RootRenderer` for consistency
- Batch mode (SetBatch) prevents macOS crashes (no interactive ROOT windows)
- Suppresses ROOT stdout/stderr for clean UI
- Async rendering (150 ms debounce on histogram tab) for UI responsiveness
- Preview images cached as PhotoImage references (prevents garbage collection)
- ROOT objects (TCanvas, TF1) created fresh for each render (no state accumulation)

### 5. Export & Data Management
- **SaveManager**: Handles render file I/O (PNG, PDF)
  - Coordinates with RootRenderer for image generation
  - Creates output directory automatically
  - Tracks saved filepaths for user feedback

- **ExportManager**: Handles data export (CSV, JSON)
  - Formats fit results with all cached parameters
  - Includes fit-specific calculations (FWHM/centroid for Gaussian, etc.)
  - Handles missing or failed fits gracefully

- **AdvancedSaveDialog**: Orchestrates multi-format export
  - User checks desired formats in dialog
  - Dialog coordinates SaveManager and ExportManager
  - Single "Save" button exports all checked formats
  - Returns list of all saved filepaths
  - Supports conditional formats (peak CSV only if peak_finder available)

- **SessionManager**: Workspace state persistence
  - Saves fit parameters and peaks to JSON
  - Enables save/restore workflow
  - Auto-save for crash recovery
  - Sessions stored in `~/.pyhpge_gui/sessions/`

## Output Directory Structure

### Render Outputs (SaveManager)
```
outputs/
├── histogram_name/
│   ├── histogram_name_YYYYMMDD_HHMMSS.png
│   ├── histogram_name_YYYYMMDD_HHMMSS.pdf
│   ├── histogram_name_fits_YYYYMMDD_HHMMSS.csv
│   └── histogram_name_fits_YYYYMMDD_HHMMSS.json
```

### Session Files (SessionManager)
```
~/.pyhpge_gui/sessions/
├── histogram_session_YYYYMMDD_HHMMSS.json
└── autosave/
    └── histogram_name_autosave.json
```

## Dependencies
- **ROOT (PyROOT)** - Nuclear physics data analysis framework with TH1, TF1, TSpectrum, TFitResult
- **Tkinter** - GUI framework (built-in Python)
- **Pillow (PIL)** - Image processing for rendering and conversion
- **NumPy** - Numerical operations
- **Python 3.10+** - Type hints (PEP 604), string formatting

## Testing Checklist

### Fit Tab Core Functionality
- [ ] Add fit with default parameters
- [ ] Fit Function dropdown (gaus, landau, expo, pol1, pol2, pol3)
- [ ] Parameter frame updates correctly for each fit function
- [ ] Energy/Width validation prevents invalid fits
- [ ] Fit button executes fit and displays results
- [ ] Results show chi-square, NDF, reduced chi-square, parameters, errors
- [ ] Gaussian fits show FWHM (2.355 * sigma), centroid (p1), area (p0 * p2 * sqrt(2pi))
- [ ] Landau fits show most probable value (p1), width (p2)
- [ ] Fit options (e.g., "SQ") applied to ROOT fit
- [ ] Parameter edits trigger auto-refit (500 ms debounce)
- [ ] Fit preview image displays correctly
- [ ] Save button opens AdvancedSaveDialog with fit_states
- [ ] Export CSV/JSON buttons create files
- [ ] Multiple fits exist simultaneously
- [ ] Selecting fit in dropdown shows correct UI

### Dropdown Fit Selection (Feb 2026)
- [ ] Dropdown displays all fits with format "Fit N (energy keV)"
- [ ] Selecting fit in dropdown shows its UI
- [ ] Adding new fit updates dropdown values
- [ ] Fit frames visibility toggles correctly
- [ ] Switching between fits preserves state
- [ ] Fit IDs remain consistent

### Auto-Fit Integration (Feb 2026)
- [ ] Auto Fit button clears old fits
- [ ] Auto Fit creates fit tabs for each peak
- [ ] Each fit tab auto-executes fit
- [ ] Results appear in dropdown-based selection
- [ ] Dropdown shows all auto-fits with energies
- [ ] Peak fits use 10 keV fixed width
- [ ] Sequential creation prevents race conditions
- [ ] UI switches to Fit tab after auto-fit

### Peak Finder
- [ ] Find Peaks detects peaks via TSpectrum
- [ ] Auto Fit integration works (not broken by Feb 2026 changes)
- [ ] Manual peak entry works
- [ ] Clear removes all peaks
- [ ] Peak displays update correctly
- [ ] Peak source tracking works

### Export & Save
- [ ] Advanced Save dialog appears
- [ ] Dialog shows correct format options
- [ ] PNG export creates valid image
- [ ] PDF export creates valid PDF
- [ ] CSV export has correct columns
- [ ] JSON export has correct structure
- [ ] Peak export includes correct data
- [ ] Export handles missing fits gracefully

### Rendering & Visualization
- [ ] Histogram renders with 16:9 aspect ratio
- [ ] Log scale controls work
- [ ] Axis range controls work
- [ ] Fit preview image displays
- [ ] Fit curve overlays correctly
- [ ] Peak markers display for manual peaks
- [ ] Title customization works

## Recent Updates (February 2026)

### 1. Dropdown-Based Fit Selection
- Converted from notebook (tab-based) system to dropdown combobox
- Benefits: cleaner UI, better scaling, more space for preview/results
- Fit frames managed via `fit_frames` dict with visibility toggling
- All fits stored in `fit_states` dict and accessible without rebuilding UI

### 2. Auto-Fit Peak Integration Fix
- Updated `peak_finder_tab.py._auto_fit_peaks()` to work with dropdown system
- Previous: referenced old `fit_tabs_notebook` and `.forget()` method
- Current: clears `fit_frames` dict and dropdown values properly
- Creates fits sequentially with 200 ms delays to prevent race conditions
- Switches to Fit tab after auto-fit completes

### 3. Documentation Updates
- Created comprehensive IMPLEMENTATION_SUMMARY.md with full technical details
- Updated USER_GUIDE.md with workflow examples
- Updated AGENT_CONTEXT.md for AI agent handoff

## Future Enhancements
1. **Undo/Redo** for fit parameters
2. **Fit comparison** - overlay multiple fits on histogram
3. **Batch calibration** - energy calibration across multiple peaks
4. **Statistical analysis** - peak uncertainties and correlations
5. **Custom fit functions** - user-defined fitting functions
6. **Live parameter adjustment** - slider-based parameter control
7. **Multi-file analysis** - compare fits across ROOT files
8. **Peak refinement** - iterative peak detection with validation

## Development Notes for Future Agents

### Critical Code Patterns

1. **Caching ROOT Results Immediately**:
   - ROOT TFitResult objects become invalid after execution
   - Must cache all results to native Python types immediately via `_cache_fit_results()`
   - Never trust ROOT objects after their execution context ends

2. **Batch Mode Rendering**:
   - All ROOT operations use batch mode (SetBatch(True))
   - Prevents macOS interactive window crashes
   - Necessary for Tkinter GUI stability

3. **Debouncing for Performance**:
   - Parameter edits: 500 ms debounce before refit
   - Rendering: 150 ms debounce on histogram tab
   - Prevents excessive computation during rapid user interactions

4. **Frame Visibility Toggling**:
   - Instead of creating/destroying tabs, toggle frame visibility
   - All fit frames created once and stored in `fit_frames` dict
   - `pack_forget()`/`pack()` used for visibility control
   - More efficient than tab recreation

5. **Dropdown Value Management**:
   - Dropdown is readonly (prevents user typing)
   - Values updated programmatically via `config(values=[...])`
   - Selection tracked separately in `current_fit_id`
   - Provides clean UI for many items

### Common Gotchas

1. **PhotoImage References**:
   - Must store PhotoImage reference to prevent garbage collection
   - Stored in `fit_state["image_ref"]` for this reason
   - Without reference, image disappears from display

2. **ROOT Object Invalidation**:
   - TFitResult, TF1, TCanvas objects can become invalid
   - Always cache to native Python before using elsewhere
   - Use batch mode to prevent interactive state accumulation

3. **Dictionary Key Management**:
   - fit_id is integer (from fit_count)
   - fit_name is "Fit N (energy)" string for dropdown display
   - Both map to same fit_state
   - Must maintain consistency across updates

4. **Deferred Execution**:
   - Auto-fit uses 100 ms delay before execution
   - Sequential fit creation uses 200 ms delays
   - Prevents race conditions and resource exhaustion
   - Important for responsive UI

### Debugging Tips

1. Enable ROOT verbose output (remove output suppression temporarily)
2. Print fit_states dict to verify state persistence
3. Check `has_fit` flag before displaying results
4. Verify dropout values match stored fit_ids
5. Test with multiple fits (≥3) to catch visibility bugs
6. Check PhotoImage references with `id()` to debug garbage collection
7. Use `app.after(0, callback)` for immediate scheduling vs `app.after(N, callback)` for delayed

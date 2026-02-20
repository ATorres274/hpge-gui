"""Histogram preview renderer — per-histogram UI panel with controls.

Extracted from ``histogram_tab.py`` so that ``HistogramTab`` stays focused on
managing *multiple* open histograms while this module handles the per-histogram
UI layout and event wiring.

Architecture note
-----------------
This file lives in ``tab_managers/`` so it is allowed to import ``tkinter``.
All *computation* (axis defaults, scroll arithmetic, range validation, options
assembly) is delegated to ``HistogramControlsModule`` in ``modules/``.
All *peak data* management is delegated to ``PeakFinderModule`` in ``modules/``.
All *fitting* computation and state is delegated to ``FitModule`` in ``modules/``.
This class owns only the UI layout and event-wiring glue.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk

from modules.error_dispatcher import get_dispatcher, ErrorLevel
from modules.fit_module import FitModule
from modules.histogram_controls_module import HistogramControlsModule
from modules.peak_manager import PeakFinderModule
from features.fit_feature import FitFeature, FIT_FUNCTIONS


class HistogramPreviewRenderer:
    """Renders individual histogram preview with interactive controls.

    Handles rendering, axis controls, range adjustments, log scale toggles,
    and the fitting panel for a single histogram preview within the HistogramTab.
    """

    def __init__(self) -> None:
        self._pending_after: dict = {"id": None}
        self._dispatcher = get_dispatcher()

        # Fit panel state — populated lazily in build_histogram_tab
        self._fit_module: FitModule | None = None
        self._fit_frames: dict[int, ttk.Frame] = {}
        self._fit_ui_states: dict[int, dict] = {}
        self._fit_dropdown_var: tk.StringVar | None = None
        self._fit_dropdown: ttk.Combobox | None = None
        self._fit_container: ttk.Frame | None = None
        self._fit_preview_label: tk.Label | None = None
        self._fit_result_text: tk.Text | None = None

    # ------------------------------------------------------------------
    # Top-level UI builder
    # ------------------------------------------------------------------

    def build_histogram_tab(
        self, app, parent_container: ttk.Frame, obj, root_path: str, path: str
    ) -> ttk.Frame:
        """Build the complete per-histogram panel inside *parent_container*.

        Returns the outermost frame so callers can pack/grid it.
        """
        try:
            self._app = app
        except Exception:
            self._app = None

        # Store root_path and path so the Save dialog can identify the histogram
        self._root_path = root_path
        self._hist_path = path

        main_frame = ttk.Frame(parent_container)
        main_frame.pack(fill=tk.BOTH, expand=True)

        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Controls area — compact, never expands vertically
        controls_frame = ttk.Frame(content_frame)
        controls_frame.pack(fill=tk.X, side=tk.TOP)

        top_sep = ttk.Separator(controls_frame, orient="horizontal")
        top_sep.pack(fill=tk.X, padx=4, pady=(2, 2))

        middle_bar = ttk.Frame(controls_frame)
        middle_bar.pack(fill=tk.X, padx=4, pady=(0, 0))

        # Preview area — left: histogram, right: fit preview (same width)
        preview_frame = ttk.Frame(content_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        hist_area = ttk.Frame(preview_frame)
        hist_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_label = tk.Label(hist_area, bg="white")
        preview_label.pack(fill=tk.BOTH, expand=True)

        ttk.Separator(preview_frame, orient="vertical").pack(
            side=tk.LEFT, fill=tk.Y, padx=1
        )

        fit_area = ttk.Frame(preview_frame)
        fit_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fit_result_text = tk.Text(fit_area, height=6, wrap=tk.WORD, state=tk.DISABLED)
        fit_result_text.pack(fill=tk.X, padx=4, pady=(4, 0))
        self._fit_result_text = fit_result_text
        fit_preview_label = tk.Label(fit_area, text="No fit yet", bg="white", fg="gray")
        fit_preview_label.pack(fill=tk.BOTH, expand=True)
        self._fit_preview_label = fit_preview_label

        self._preview_label = preview_label
        self._current_obj = obj

        # Re-render on window resize
        try:
            toplevel = preview_label.winfo_toplevel()
            def _on_config(event):  # noqa: ANN001
                try:
                    self.render_preview(self._current_obj)
                except Exception:
                    pass
            toplevel.bind("<Configure>", _on_config)
        except Exception:
            pass

        # Build controls, peak panel, and fit panel
        try:
            defaults = HistogramControlsModule.compute_defaults(obj)
            axis_controls = ttk.Frame(middle_bar)
            axis_controls.pack(side=tk.LEFT, anchor="nw", padx=2, pady=(0, 0))
            self._build_axis_controls(axis_controls, app, defaults)
            self._build_peak_panel(middle_bar, app, obj)
        except Exception:
            pass

        try:
            self._fit_module = FitModule()
            self._fit_module.set_fit_completed_callback(self._on_fit_completed)
            self._fit_module.set_histogram(obj)
            self._build_fit_panel(middle_bar)
        except Exception:
            pass

        bottom_sep = ttk.Separator(controls_frame, orient="horizontal")
        bottom_sep.pack(fill=tk.X, padx=4, pady=(2, 0))

        return main_frame

    # ------------------------------------------------------------------
    # Axis controls grid
    # ------------------------------------------------------------------

    def _build_axis_controls(self, axis_controls: ttk.Frame, app, defaults: dict) -> None:
        """Populate *axis_controls* with the 6-row range/label/extras grid.

        Sets instance vars consumed by ``render_preview`` and ``_schedule_render``:
        ``_xmin_var``, ``_xmax_var``, ``_ymin_var``, ``_ymax_var``,
        ``_logx_var``, ``_logy_var``, ``_xlabel_var``, ``_ylabel_var``,
        ``_title_var``, ``_show_markers_var``,
        ``_x_hard_min``, ``_x_hard_max``, ``_y_hard_min``,
        ``_reset_controls``.

        Y max is intentionally **unclamped** on the upper end — ROOT allows
        the Y axis range to exceed the histogram's data maximum, so users can
        freely scroll/type above the preset value.  X max is hard-clamped to
        the histogram's original X axis maximum.
        """
        x_min_default = defaults["x_min"]
        x_max_default = defaults["x_max"]
        y_min_default = defaults["y_min"]
        y_max_default = defaults["y_max"]
        x_scroll_step = defaults["x_scroll_step"]
        y_scroll_step = defaults["y_scroll_step"]

        # StringVars — always display exactly one decimal place
        self._xmin_var = tk.StringVar(value=f"{x_min_default:.1f}")
        self._xmax_var = tk.StringVar(value=f"{x_max_default:.1f}")
        self._ymin_var = tk.StringVar(value=f"{y_min_default:.1f}")
        self._ymax_var = tk.StringVar(value=f"{y_max_default:.1f}")

        # Log scale toggles (log Y enabled by default for HPGe spectra)
        self._logx_var = tk.BooleanVar(value=False)
        self._logy_var = tk.BooleanVar(value=True)

        # Axis label / title vars
        self._xlabel_var = tk.StringVar(value=defaults["x_label"])
        self._ylabel_var = tk.StringVar(value=defaults["y_label"])
        self._title_var  = tk.StringVar(value=defaults["title"])

        # Show-markers toggle (on by default)
        self._show_markers_var = tk.BooleanVar(value=True)

        # Hard limits: X is clamped to original axis range; Y max is unclamped
        self._x_hard_min = x_min_default
        self._x_hard_max = x_max_default
        self._y_hard_min = y_min_default
        _Y_MAX_LIMIT = float("inf")

        # --- Row 0: Title ---
        ttk.Label(axis_controls, text="Title:").grid(
            row=0, column=0, sticky="e", padx=(2, 2), pady=(2, 2))
        ttk.Entry(axis_controls, textvariable=self._title_var, width=30).grid(
            row=0, column=1, columnspan=3, padx=(0, 4), pady=(2, 2))

        # --- Row 1: X range ---
        x_min_entry, x_max_entry = self._build_range_row(
            axis_controls, row=1, label="X:",
            min_var=self._xmin_var, max_var=self._xmax_var,
            log_var=self._logx_var, log_label="Log X",
        )
        self._bind_range_entry(
            x_min_entry, x_max_entry,
            min_var=self._xmin_var, max_var=self._xmax_var,
            hard_min=self._x_hard_min, hard_max=self._x_hard_max,
            scroll_step=x_scroll_step,
            log_var=self._logx_var,
        )

        # --- Row 2: X label ---
        ttk.Label(axis_controls, text="X label:").grid(
            row=2, column=0, sticky="e", padx=(2, 2), pady=(1, 2))
        ttk.Entry(axis_controls, textvariable=self._xlabel_var, width=30).grid(
            row=2, column=1, columnspan=3, padx=(0, 4), pady=(1, 2))

        # --- Row 3: Y range ---
        y_min_entry, y_max_entry = self._build_range_row(
            axis_controls, row=3, label="Y:",
            min_var=self._ymin_var, max_var=self._ymax_var,
            log_var=self._logy_var, log_label="Log Y",
        )
        self._bind_range_entry(
            y_min_entry, y_max_entry,
            min_var=self._ymin_var, max_var=self._ymax_var,
            hard_min=self._y_hard_min, hard_max=_Y_MAX_LIMIT,
            scroll_step=y_scroll_step,
            log_var=self._logy_var,
        )

        # --- Row 4: Y label ---
        ttk.Label(axis_controls, text="Y label:").grid(
            row=4, column=0, sticky="e", padx=(2, 2), pady=(1, 2))
        ttk.Entry(axis_controls, textvariable=self._ylabel_var, width=30).grid(
            row=4, column=1, columnspan=3, padx=(0, 4), pady=(1, 2))

        # --- Row 5: Show Markers + Reset ---
        extras_frame = ttk.Frame(axis_controls)
        extras_frame.grid(row=5, column=0, columnspan=5, sticky="w",
                          padx=(2, 2), pady=(2, 4))
        ttk.Checkbutton(
            extras_frame, text="Show Markers",
            variable=self._show_markers_var,
            command=lambda: self._schedule_render(),
        ).pack(side=tk.LEFT, padx=(0, 8))

        def _reset_controls():
            self._xmin_var.set(f"{x_min_default:.1f}")
            self._xmax_var.set(f"{x_max_default:.1f}")
            self._ymin_var.set(f"{y_min_default:.1f}")
            self._ymax_var.set(f"{y_max_default:.1f}")
            self._logx_var.set(False)
            self._logy_var.set(True)
            self._show_markers_var.set(True)
            self._xlabel_var.set(defaults["x_label"])
            self._ylabel_var.set(defaults["y_label"])
            self._title_var.set(defaults["title"])
            self._schedule_render()

        self._reset_controls = _reset_controls
        ttk.Button(extras_frame, text="Reset", command=_reset_controls).pack(side=tk.LEFT)
        ttk.Button(
            extras_frame, text="Save",
            command=lambda: self._open_save_dialog(),
        ).pack(side=tk.LEFT, padx=(6, 0))

        # Auto-render on every keystroke / paste in any entry field
        def _on_any_change(*_):
            self._schedule_render()

        for _var in (self._xmin_var, self._xmax_var,
                     self._ymin_var, self._ymax_var,
                     self._xlabel_var, self._ylabel_var, self._title_var):
            _var.trace_add("write", _on_any_change)

    def _build_range_row(
        self,
        grid: ttk.Frame,
        row: int,
        label: str,
        min_var: tk.StringVar,
        max_var: tk.StringVar,
        log_var: tk.BooleanVar,
        log_label: str,
    ) -> tuple[ttk.Entry, ttk.Entry]:
        """Add one axis-range row to *grid* and return the (min, max) entry widgets."""
        ttk.Label(grid, text=label).grid(
            row=row, column=0, sticky="e", padx=(2, 2), pady=(2, 1))
        min_entry = ttk.Entry(grid, textvariable=min_var, width=8)
        min_entry.grid(row=row, column=1, padx=(0, 2), pady=(2, 1))
        ttk.Label(grid, text="to").grid(row=row, column=2, padx=2, pady=(2, 1))
        max_entry = ttk.Entry(grid, textvariable=max_var, width=8)
        max_entry.grid(row=row, column=3, padx=(0, 4), pady=(2, 1))
        ttk.Checkbutton(
            grid, text=log_label, variable=log_var,
            command=lambda: self._schedule_render(),
        ).grid(row=row, column=4, padx=(0, 2), pady=(2, 1))
        return min_entry, max_entry

    def _bind_range_entry(
        self,
        min_entry: ttk.Entry,
        max_entry: ttk.Entry,
        *,
        min_var: tk.StringVar,
        max_var: tk.StringVar,
        hard_min: float,
        hard_max: float,
        scroll_step: float,
        log_var: tk.BooleanVar,
    ) -> None:
        """Attach focus-out/Return/scroll bindings to a pair of range entries.

        Validation is delegated to ``HistogramControlsModule``; scroll
        direction is detected via ``HistogramControlsModule.detect_scroll_direction``.
        """
        def _format_min(event=None):  # noqa: ANN001
            result = HistogramControlsModule.validate_min(
                min_var.get(), max_var.get(), hard_min=hard_min)
            if result is not None:
                min_var.set(result)
            self._schedule_render()

        def _format_max(event=None):  # noqa: ANN001
            # Y max has no hard upper cap when hard_max is inf
            kw: dict = {} if hard_max == float("inf") else {"hard_max": hard_max}
            result = HistogramControlsModule.validate_max(
                max_var.get(), min_var.get(), **kw)
            if result is not None:
                max_var.set(result)
            self._schedule_render()

        for evt in ("<FocusOut>", "<Return>"):
            min_entry.bind(evt, _format_min)
            max_entry.bind(evt, _format_max)

        for scroll_evt in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            min_entry.bind(scroll_evt, lambda e, mv=min_var, xv=max_var: self._on_min_scroll(
                e, mv, xv, hard_min, hard_max, scroll_step,
                log_mode=log_var.get()))
            max_entry.bind(scroll_evt, lambda e, mv=max_var, xv=min_var: self._on_max_scroll(
                e, mv, xv, hard_min, hard_max, scroll_step,
                log_mode=log_var.get()))

    # ------------------------------------------------------------------
    # Peak finder panel
    # ------------------------------------------------------------------

    def _build_peak_panel(self, middle_bar: object, app: object, obj: object) -> None:
        """Build the peak-finder panel and attach it to *middle_bar*.

        Extracted from ``build_histogram_tab`` so that method stays focused on
        the axis-controls grid.  Initialises ``self._peak_finder`` and wires all
        treeview/button events.
        """
        vsep = ttk.Separator(middle_bar, orient="vertical")
        vsep.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 8), pady=2)

        peak_panel = ttk.Frame(middle_bar)
        peak_panel.pack(side=tk.LEFT, anchor="nw", padx=(0, 4))

        self._peak_finder = PeakFinderModule()
        self._peak_finder.current_hist = obj
        self._peak_finder.parent_app = app

        ttk.Label(peak_panel, text="Peaks", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 2))

        tree_frame = ttk.Frame(peak_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        peaks_tree = ttk.Treeview(
            tree_frame,
            columns=("energy", "counts", "source"),
            show="headings",
            selectmode="extended",
            height=4,
        )
        peaks_tree.heading("energy", text="Energy (keV)")
        peaks_tree.heading("counts", text="Counts")
        peaks_tree.heading("source", text="Source")
        peaks_tree.column("energy", width=80, anchor="center")
        peaks_tree.column("counts", width=60, anchor="center")
        peaks_tree.column("source", width=60, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=peaks_tree.yview)
        peaks_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        peaks_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        def _on_peak_double(event):  # noqa: ANN001
            sel = peaks_tree.selection()
            if not sel:
                return
            iid = sel[0]
            try:
                current_val = self._peak_finder.get_peak_energy_by_iid(iid)
                new_energy = simpledialog.askfloat(
                    "Edit peak energy", "Energy (keV):",
                    initialvalue=current_val, parent=app,
                )
                if new_energy is None:
                    return
                if self._peak_finder.set_peak_energy_by_iid(iid, float(new_energy)):
                    self._schedule_render()
            except Exception:
                pass

        peaks_tree.bind("<Double-1>", _on_peak_double)
        peaks_tree.bind(
            "<Delete>",
            lambda e: (self._peak_finder.remove_selected_peak(), self._schedule_render()),
        )

        tree_menu = tk.Menu(peaks_tree, tearoff=0)
        tree_menu.add_command(label="Edit peak", command=lambda: _on_peak_double(None))
        tree_menu.add_command(
            label="Remove peak",
            command=lambda: (self._peak_finder.remove_selected_peak(), self._schedule_render()),
        )

        def _show_peak_menu(event):  # noqa: ANN001
            iid = peaks_tree.identify_row(event.y)
            if iid:
                try:
                    if iid not in peaks_tree.selection():
                        peaks_tree.selection_set(iid)
                except Exception:
                    pass
            try:
                tree_menu.tk_popup(event.x_root, event.y_root)
            finally:
                try:
                    tree_menu.grab_release()
                except Exception:
                    pass

        peaks_tree.bind("<Button-3>", _show_peak_menu)
        peaks_tree.bind("<Button-2>", _show_peak_menu)
        peaks_tree.bind("<Control-Button-1>", _show_peak_menu)

        self._peak_finder.setup(app, peaks_tree, None)
        self._peak_finder._render_callback = lambda: self._schedule_render()

        # --- Manual peak entry row ---
        peak_controls = ttk.Frame(peak_panel)
        peak_controls.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(peak_controls, text="Manual (keV):").pack(side=tk.LEFT, padx=(0, 2))
        manual_peak_var = tk.StringVar(value="")
        self._peak_finder._manual_peak_var = manual_peak_var
        manual_entry = ttk.Entry(peak_controls, textvariable=manual_peak_var, width=8)
        manual_entry.pack(side=tk.LEFT, padx=(0, 2))

        def _on_manual_enter(event):  # noqa: ANN001
            try:
                self._peak_finder._add_manual_peak()
                self._schedule_render()
            except Exception:
                pass
            return "break"

        manual_entry.bind("<Return>", _on_manual_enter)
        manual_entry.bind("<KP_Enter>", _on_manual_enter)

        ttk.Button(
            peak_controls, text="Add",
            command=lambda: (self._peak_finder._add_manual_peak(), self._schedule_render()),
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            peak_controls, text="Find Peaks",
            command=lambda: self._peak_finder._find_peaks(app),
        ).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(
            peak_controls, text="Clear",
            command=lambda: (self._peak_finder._clear_peaks(), self._schedule_render()),
        ).pack(side=tk.LEFT, padx=(0, 2))

        # --- Search options row ---
        self._build_peak_search_options(peak_panel, app)

        try:
            app.after(200, lambda: self._peak_finder._find_peaks(app))
        except Exception:
            pass

    def _build_peak_search_options(self, peak_panel: ttk.Frame, app) -> None:
        """Build the peak-search refinement controls below the manual entry row.

        Exposes sigma (TSpectrum resolution), energy range, and minimum-counts
        threshold so the user can focus automatic search on a sub-range of the
        spectrum (e.g. above the Compton edge, or at higher energies where
        background is low).  Changes take effect on the next "Find Peaks" call.
        """
        # Separator + collapsible label
        ttk.Separator(peak_panel, orient="horizontal").pack(fill=tk.X, pady=(4, 2))

        search_opts = ttk.Frame(peak_panel)
        search_opts.pack(fill=tk.X, pady=(0, 2))

        # --- Row 0: Sigma ---
        row0 = ttk.Frame(search_opts)
        row0.pack(fill=tk.X, pady=(1, 1))
        ttk.Label(row0, text="Sigma:").pack(side=tk.LEFT, padx=(0, 2))
        self._sigma_var = tk.StringVar(value="3")
        sigma_spin = ttk.Spinbox(
            row0, textvariable=self._sigma_var,
            from_=1, to=20, increment=1, width=4,
        )
        sigma_spin.pack(side=tk.LEFT, padx=(0, 8))

        # Tooltip-style help
        ttk.Label(row0, text="(TSpectrum σ)", foreground="gray").pack(side=tk.LEFT)

        # --- Row 1: Energy range ---
        row1 = ttk.Frame(search_opts)
        row1.pack(fill=tk.X, pady=(1, 1))
        ttk.Label(row1, text="E range:").pack(side=tk.LEFT, padx=(0, 2))
        self._search_emin_var = tk.StringVar(value="")
        ttk.Entry(row1, textvariable=self._search_emin_var, width=7).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(row1, text="–").pack(side=tk.LEFT, padx=(0, 2))
        self._search_emax_var = tk.StringVar(value="")
        ttk.Entry(row1, textvariable=self._search_emax_var, width=7).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(row1, text="keV", foreground="gray").pack(side=tk.LEFT)

        # --- Row 2: Minimum counts threshold ---
        row2 = ttk.Frame(search_opts)
        row2.pack(fill=tk.X, pady=(1, 2))
        ttk.Label(row2, text="Min counts:").pack(side=tk.LEFT, padx=(0, 2))
        self._search_threshold_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self._search_threshold_var, width=8).pack(side=tk.LEFT)

        def _apply_search_params(*_args) -> None:
            """Push current control values into ``PeakFinderModule``."""
            try:
                sigma = float(self._sigma_var.get())
            except (ValueError, AttributeError):
                sigma = 3.0
            try:
                raw_emin = self._search_emin_var.get().strip()
                emin = float(raw_emin) if raw_emin else None
            except (ValueError, AttributeError):
                emin = None
            try:
                raw_emax = self._search_emax_var.get().strip()
                emax = float(raw_emax) if raw_emax else None
            except (ValueError, AttributeError):
                emax = None
            try:
                threshold = float(self._search_threshold_var.get())
            except (ValueError, AttributeError):
                threshold = 0.0

            pf = getattr(self, "_peak_finder", None)
            if pf is not None:
                pf.search_sigma = sigma
                pf.search_energy_min = emin
                pf.search_energy_max = emax
                pf.search_threshold_counts = threshold

        # Bind so params are applied whenever the user edits them (on Return/FocusOut)
        for widget_var in (self._sigma_var, self._search_emin_var,
                           self._search_emax_var, self._search_threshold_var):
            widget_var.trace_add("write", lambda *_: _apply_search_params())

    # ------------------------------------------------------------------
    # Fit panel
    # ------------------------------------------------------------------

    def _build_fit_panel(self, middle_bar: ttk.Frame) -> None:
        """Build the compact fitting control panel in *middle_bar*."""
        vsep = ttk.Separator(middle_bar, orient="vertical")
        vsep.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 8), pady=2)

        fit_panel = ttk.Frame(middle_bar)
        fit_panel.pack(side=tk.LEFT, anchor="nw", padx=(0, 4))

        ttk.Label(
            fit_panel, text="Fits", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w", pady=(0, 2))

        # Dropdown + Add button
        header = ttk.Frame(fit_panel)
        header.pack(fill=tk.X, pady=(0, 2))
        self._fit_dropdown_var = tk.StringVar(value="")
        self._fit_dropdown = ttk.Combobox(
            header,
            textvariable=self._fit_dropdown_var,
            values=[],
            state="readonly",
            width=20,
        )
        self._fit_dropdown.pack(side=tk.LEFT, padx=(0, 4))
        self._fit_dropdown.bind(
            "<<ComboboxSelected>>", lambda e: self._on_fit_dropdown_changed()
        )
        ttk.Button(header, text="+ Fit", command=self._fit_add).pack(side=tk.LEFT)

        # Container that shows the active fit's compact controls
        self._fit_container = ttk.Frame(fit_panel)
        self._fit_container.pack(fill=tk.X, pady=(0, 2))

    def _fit_add(
        self,
        energy: float | None = None,
        width: float | None = None,
        peak_idx: int | None = None,
    ) -> None:
        """Create a new fit entry and show its compact controls card."""
        if self._fit_module is None:
            return
        fit_id = self._fit_module.add_fit(energy=energy, width=width, peak_idx=peak_idx)
        fit_name = self._fit_module.get_fit_display_name(fit_id)

        card = ttk.Frame(self._fit_container)
        ui_state = self._fit_build_card(card, fit_id, energy=energy, width=width)
        self._fit_frames[fit_id] = card
        self._fit_ui_states[fit_id] = ui_state

        vals = list(self._fit_dropdown.cget("values"))
        vals.append(fit_name)
        self._fit_dropdown.config(values=vals)
        self._fit_dropdown.set(fit_name)
        self._fit_show_frame(fit_id)

    def _fit_build_card(
        self,
        card: ttk.Frame,
        fit_id: int,
        energy: float | None = None,
        width: float | None = None,
    ) -> dict:
        """Build compact per-fit controls inside *card* and return ui_state."""
        ui_state: dict = {
            "fit_func_var":    tk.StringVar(value="gaus"),
            "fit_options_var": tk.StringVar(value="SQ"),
            "energy_var":      tk.StringVar(value=f"{energy:.2f}" if energy is not None else ""),
            "width_var":       tk.StringVar(value=str(width) if width is not None else ""),
            "param_entries":   [],
            "param_fixed_vars": [],
            "params_frame":    None,
            "refit_pending":   {"id": None},
        }

        row0 = ttk.Frame(card)
        row0.pack(fill=tk.X, pady=(0, 1))

        ttk.Label(row0, text="Func:").pack(side=tk.LEFT, padx=(0, 2))
        func_combo = ttk.Combobox(
            row0, textvariable=ui_state["fit_func_var"],
            values=FIT_FUNCTIONS, state="readonly", width=14,
        )
        func_combo.pack(side=tk.LEFT, padx=(0, 6))
        func_combo.bind(
            "<<ComboboxSelected>>",
            lambda e, us=ui_state: self._fit_on_func_changed(us),
        )

        ttk.Label(row0, text="E:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Entry(row0, textvariable=ui_state["energy_var"], width=7).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Label(row0, text="W:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Entry(row0, textvariable=ui_state["width_var"], width=7).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Label(row0, text="Opt:").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Entry(row0, textvariable=ui_state["fit_options_var"], width=5).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(
            row0, text="Fit",
            command=lambda fid=fit_id: self._fit_trigger(fid),
        ).pack(side=tk.LEFT)

        # Params row
        params_frame = ttk.LabelFrame(card, text="Initial Parameters (gaus)")
        params_frame.pack(fill=tk.X, pady=(2, 1))
        ui_state["params_frame"] = params_frame
        self._fit_rebuild_params(ui_state, FitFeature.get_param_labels("gaus"))

        return ui_state

    def _fit_rebuild_params(self, ui_state: dict, param_names: list[str]) -> None:
        """Destroy and recreate parameter entry widgets in the params frame."""
        frame = ui_state["params_frame"]
        for w in frame.winfo_children():
            w.destroy()
        ui_state["param_entries"] = []
        ui_state["param_fixed_vars"] = []
        for i, name in enumerate(param_names):
            ttk.Label(frame, text=f"{name}:").grid(
                row=0, column=i * 3, sticky="e", padx=(4, 2)
            )
            var = tk.StringVar(value="")
            ttk.Entry(frame, textvariable=var, width=8).grid(
                row=0, column=i * 3 + 1, sticky="w", padx=(0, 2)
            )
            var.trace_add("write", lambda *_, us=ui_state: self._fit_schedule_refit(us))
            fixed_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text="Fix", variable=fixed_var).grid(
                row=0, column=i * 3 + 2, sticky="w", padx=(0, 8)
            )
            ui_state["param_entries"].append(var)
            ui_state["param_fixed_vars"].append(fixed_var)

    # ------------------------------------------------------------------
    # Fit event handlers
    # ------------------------------------------------------------------

    def _on_fit_dropdown_changed(self) -> None:
        if self._fit_module is None or self._fit_dropdown_var is None:
            return
        selected = self._fit_dropdown_var.get()
        for fit_id, name in self._fit_module.list_fits():
            if name == selected:
                self._fit_show_frame(fit_id)
                return

    def _fit_show_frame(self, fit_id: int) -> None:
        for frame in self._fit_frames.values():
            frame.pack_forget()
        if fit_id in self._fit_frames:
            self._fit_frames[fit_id].pack(fill=tk.X)

    def _fit_on_func_changed(self, ui_state: dict) -> None:
        fit_func = ui_state["fit_func_var"].get()
        new_labels = FitFeature.get_param_labels(fit_func)
        if len(new_labels) != len(ui_state["param_entries"]):
            self._fit_rebuild_params(ui_state, new_labels)
        ui_state["params_frame"].configure(
            text=f"Initial Parameters ({fit_func})"
        )

    def _fit_schedule_refit(self, ui_state: dict) -> None:
        app = getattr(self, "_app", None)
        if app is None:
            return
        if ui_state["refit_pending"]["id"] is not None:
            try:
                app.after_cancel(ui_state["refit_pending"]["id"])
            except Exception:
                pass
        for fid, us in self._fit_ui_states.items():
            if us is ui_state:
                ui_state["refit_pending"]["id"] = app.after(
                    600, lambda fid=fid: self._fit_trigger(fid)
                )
                return

    def _fit_trigger(self, fit_id: int) -> None:
        """Read UI vars, push to FitModule, execute the fit."""
        if self._fit_module is None:
            return
        ui_state = self._fit_ui_states.get(fit_id)
        if ui_state is None:
            return

        fit_func    = ui_state["fit_func_var"].get()
        fit_options = ui_state["fit_options_var"].get().strip() or "SQ"

        try:
            e = ui_state["energy_var"].get().strip()
            energy = float(e) if e else None
        except ValueError:
            energy = None

        try:
            w = ui_state["width_var"].get().strip()
            width = float(w) if w else None
        except ValueError:
            width = None

        params: list[float] = []
        for v in ui_state["param_entries"]:
            raw = v.get().strip()
            if not raw:
                continue
            try:
                params.append(float(raw))
            except ValueError as exc:
                self._dispatcher.emit(
                    ErrorLevel.WARNING,
                    f"Non-numeric param ignored: {raw!r}",
                    context="HistogramPreviewRenderer._fit_trigger",
                    exception=exc,
                )

        fixed_params = [v.get() for v in ui_state["param_fixed_vars"]]

        self._fit_module.update_fit_params(
            fit_id,
            fit_func=fit_func,
            energy=energy,
            width=width,
            params=params,
            fixed_params=fixed_params,
            fit_options=fit_options,
        )

        root = self._fit_module.get_root_module(getattr(self, "_app", None))
        if root is None:
            return
        self._fit_module.perform_fit(fit_id, root)

    def _on_fit_completed(self, fit_id: int, cached: dict) -> None:
        """Called by FitModule after a fit: update results text + preview."""
        state = self._fit_module.get_fit_state(fit_id) if self._fit_module else None
        if state is not None:
            text = FitFeature.format_fit_results(
                state.get("fit_func", "gaus"),
                state.get("fit_options", "SQ"),
                cached,
            )
            if self._fit_result_text is not None:
                try:
                    self._fit_result_text.config(state=tk.NORMAL)
                    self._fit_result_text.delete("1.0", tk.END)
                    self._fit_result_text.insert(tk.END, text)
                    self._fit_result_text.config(state=tk.DISABLED)
                except Exception:
                    pass

        # Render the fitted histogram clone into the fit preview label.
        pm = getattr(self, "_preview_manager", None)
        fit_label = self._fit_preview_label
        if pm is not None and fit_label is not None and self._fit_module is not None:
            root = self._fit_module.get_root_module(getattr(self, "_app", None))
            clone = self._fit_module.current_hist_clone
            if root is not None and clone is not None:
                try:
                    pm.render_into_label_async(root, clone, fit_label, options={}, delay_ms=80)
                except Exception as exc:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Fit preview render failed",
                        context="HistogramPreviewRenderer._on_fit_completed",
                        exception=exc,
                    )

    # ------------------------------------------------------------------
    # Save dialog
    # ------------------------------------------------------------------

    def _open_save_dialog(self) -> None:
        """Open the save dialog for the current histogram.

        Builds a minimal ``tk.Toplevel`` that lets the user choose PNG/PDF
        (high-resolution render) and CSV/JSON peak export.  All file I/O is
        delegated to ``SaveManager``; this method only owns the UI.
        """
        import os
        import tkinter as tk
        from tkinter import filedialog, messagebox
        from modules.save_manager import SaveManager

        app = getattr(self, "_app", None)
        obj = getattr(self, "_current_obj", None)
        root_path = getattr(self, "_root_path", "")
        root = None
        try:
            if app is not None:
                root = getattr(app, "ROOT", None)
        except Exception:
            pass

        hist_name = "histogram"
        try:
            hist_name = obj.GetName()
        except Exception:
            pass

        # ---- Build dialog ----
        dialog = tk.Toplevel(app)
        dialog.title("Save Histogram")
        dialog.resizable(False, False)
        dialog.transient(app)
        dialog.grab_set()

        pad = {"padx": 8, "pady": 4}
        frame = tk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, **pad)

        # Output directory
        tk.Label(frame, text="Output directory:").grid(row=0, column=0, sticky="e", **pad)
        default_dir = os.path.join("outputs", os.path.splitext(os.path.basename(root_path))[0])
        dir_var = tk.StringVar(value=default_dir)
        dir_entry = tk.Entry(frame, textvariable=dir_var, width=32)
        dir_entry.grid(row=0, column=1, sticky="ew", **pad)
        def _browse():
            d = filedialog.askdirectory(title="Select output directory")
            if d:
                dir_var.set(d)
        tk.Button(frame, text="…", command=_browse).grid(row=0, column=2, **pad)

        # Filename stem
        tk.Label(frame, text="Filename:").grid(row=1, column=0, sticky="e", **pad)
        name_var = tk.StringVar(value=hist_name)
        tk.Entry(frame, textvariable=name_var, width=32).grid(row=1, column=1, sticky="ew", **pad)

        # Resolution
        tk.Label(frame, text="Width (px):").grid(row=2, column=0, sticky="e", **pad)
        width_var = tk.StringVar(value="1920")
        tk.Entry(frame, textvariable=width_var, width=8).grid(row=2, column=1, sticky="w", **pad)
        tk.Label(frame, text="Height (px):").grid(row=3, column=0, sticky="e", **pad)
        height_var = tk.StringVar(value="1080")
        tk.Entry(frame, textvariable=height_var, width=8).grid(row=3, column=1, sticky="w", **pad)
        # Quick-ratio buttons
        ratio_frame = tk.Frame(frame)
        ratio_frame.grid(row=3, column=2, **pad)
        def _set_ratio(w_ratio, h_ratio):
            try:
                w = int(width_var.get())
                height_var.set(str(int(w * h_ratio / w_ratio)))
            except ValueError:
                pass
        tk.Button(ratio_frame, text="16:9", command=lambda: _set_ratio(16, 9)).pack(side=tk.LEFT, padx=2)
        tk.Button(ratio_frame, text="4:3",  command=lambda: _set_ratio(4, 3)).pack(side=tk.LEFT, padx=2)
        tk.Button(ratio_frame, text="1:1",  command=lambda: _set_ratio(1, 1)).pack(side=tk.LEFT, padx=2)

        # Format checkboxes
        tk.Label(frame, text="Formats:").grid(row=4, column=0, sticky="ne", **pad)
        fmt_frame = tk.Frame(frame)
        fmt_frame.grid(row=4, column=1, columnspan=2, sticky="w", **pad)
        png_var  = tk.BooleanVar(value=True)
        pdf_var  = tk.BooleanVar(value=True)
        csv_var  = tk.BooleanVar(value=False)
        json_var = tk.BooleanVar(value=False)
        tk.Checkbutton(fmt_frame, text="PNG (preview)",  variable=png_var).pack(anchor="w")
        tk.Checkbutton(fmt_frame, text="PDF (preview)",  variable=pdf_var).pack(anchor="w")
        tk.Checkbutton(fmt_frame, text="CSV (peaks)",    variable=csv_var).pack(anchor="w")
        tk.Checkbutton(fmt_frame, text="JSON (peaks)",   variable=json_var).pack(anchor="w")

        frame.columnconfigure(1, weight=1)

        def _do_save():
            directory = dir_var.get().strip()
            name      = name_var.get().strip()
            if not directory or not name:
                messagebox.showerror("Save", "Directory and filename are required.", parent=dialog)
                return
            try:
                width  = int(width_var.get())
                height = int(height_var.get())
            except ValueError:
                messagebox.showerror("Save", "Width and height must be integers.", parent=dialog)
                return
            if width < 100 or height < 100:
                messagebox.showerror("Save", "Width and height must be ≥ 100 px.", parent=dialog)
                return
            if not any((png_var.get(), pdf_var.get(), csv_var.get(), json_var.get())):
                messagebox.showerror("Save", "Select at least one output format.", parent=dialog)
                return

            # Assemble current render options from axis controls
            options = HistogramControlsModule.build_render_options(
                width, height,
                xmin_raw=getattr(self, "_xmin_var", None) and self._xmin_var.get() or "",
                xmax_raw=getattr(self, "_xmax_var", None) and self._xmax_var.get() or "",
                ymin_raw=getattr(self, "_ymin_var", None) and self._ymin_var.get() or "",
                ymax_raw=getattr(self, "_ymax_var", None) and self._ymax_var.get() or "",
                logx=bool(getattr(self, "_logx_var", None) and self._logx_var.get()),
                logy=bool(getattr(self, "_logy_var", None) and self._logy_var.get()),
                xtitle=getattr(self, "_xlabel_var", None) and self._xlabel_var.get() or "",
                ytitle=getattr(self, "_ylabel_var", None) and self._ylabel_var.get() or "",
                title=getattr(self, "_title_var", None) and self._title_var.get() or "",
                show_markers=bool(getattr(self, "_show_markers_var", None) and self._show_markers_var.get()),
                peak_energies=[p["energy"] for p in getattr(getattr(self, "_peak_finder", None), "peaks", [])],
            )

            save_mgr = SaveManager()
            saved: list[str] = []
            try:
                os.makedirs(directory, exist_ok=True)
                saved.extend(save_mgr.delegate_save(
                    root=root, obj=obj,
                    directory=directory, name=name,
                    width=width, height=height,
                    render_options=options,
                    png=png_var.get(), pdf=pdf_var.get(),
                ))
            except Exception as exc:
                messagebox.showerror("Save", f"Image export failed:\n{exc}", parent=dialog)
                return

            peaks = list(getattr(getattr(self, "_peak_finder", None), "peaks", []))
            # Collect completed fit states for combined export
            fit_states = (
                self._fit_module.get_all_fit_states()
                if self._fit_module is not None
                else None
            ) or None

            if csv_var.get():
                if not peaks:
                    messagebox.showwarning("Save", "No peaks to export as CSV.", parent=dialog)
                else:
                    try:
                        csv_path = os.path.join(directory, f"{name}_peaks.csv")
                        save_mgr.export_peaks_csv(peaks, name, csv_path, fit_states=fit_states)
                        saved.append(csv_path)
                    except Exception as exc:
                        messagebox.showerror("Save", f"CSV export failed:\n{exc}", parent=dialog)
                        return

            if json_var.get():
                if not peaks:
                    messagebox.showwarning("Save", "No peaks to export as JSON.", parent=dialog)
                else:
                    try:
                        json_path = os.path.join(directory, f"{name}_peaks.json")
                        save_mgr.export_peaks_json(peaks, name, json_path, fit_states=fit_states)
                        saved.append(json_path)
                    except Exception as exc:
                        messagebox.showerror("Save", f"JSON export failed:\n{exc}", parent=dialog)
                        return

            if saved:
                messagebox.showinfo(
                    "Save", "Saved:\n" + "\n".join(os.path.basename(p) for p in saved),
                    parent=dialog,
                )
            dialog.destroy()

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=(8, 4))
        tk.Button(btn_frame, text="Save", command=_do_save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_preview(self, obj) -> None:
        """Render a preview of the histogram onto the bottom preview label.

        Uses the actual label geometry so the rendered image fills the label
        exactly, with no blank white space.  Delegates all rendering work to
        the shared ``HistogramRenderer``.
        """
        label = getattr(self, "_preview_label", None)
        pm = getattr(self, "_preview_manager", None)
        if label is None:
            return

        root = None
        try:
            app = getattr(self, "_app", None)
            if app is not None:
                root = getattr(app, "ROOT", None)
        except Exception:
            root = None

        # Build render options WITHOUT target dimensions so render_into_label
        # reads the actual label size (winfo_width / winfo_height) and fills
        # the label exactly — no blank white-space padding.
        options = HistogramControlsModule.build_render_options(
            0, 0,
            xmin_raw=getattr(self, "_xmin_var", None) and self._xmin_var.get() or "",
            xmax_raw=getattr(self, "_xmax_var", None) and self._xmax_var.get() or "",
            ymin_raw=getattr(self, "_ymin_var", None) and self._ymin_var.get() or "",
            ymax_raw=getattr(self, "_ymax_var", None) and self._ymax_var.get() or "",
            logx=bool(getattr(self, "_logx_var", None) and self._logx_var.get()),
            logy=bool(getattr(self, "_logy_var", None) and self._logy_var.get()),
            xtitle=getattr(self, "_xlabel_var", None) and self._xlabel_var.get() or "",
            ytitle=getattr(self, "_ylabel_var", None) and self._ylabel_var.get() or "",
            title=getattr(self, "_title_var", None) and self._title_var.get() or "",
            show_markers=bool(getattr(self, "_show_markers_var", None) and self._show_markers_var.get()),
            peak_energies=[p["energy"] for p in getattr(getattr(self, "_peak_finder", None), "peaks", [])],
        )

        if pm:
            try:
                pm.render_into_label_async(root, obj, label, options=options, delay_ms=80)
                return
            except Exception:
                pass

        try:
            label.configure(text="No preview available", image="")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Scroll event handlers (delegate computation to module)
    # ------------------------------------------------------------------

    def _on_min_scroll(
        self, event, min_var: tk.StringVar, max_var: tk.StringVar,
        min_limit: float, max_limit: float, step: float = 0.5,
        log_mode: bool = False,
    ) -> None:
        """Handle scroll wheel on a min-value entry.

        Scroll direction is detected by ``HistogramControlsModule``; arithmetic
        is delegated to ``HistogramControlsModule.clamp_min``.
        """
        try:
            direction_down = HistogramControlsModule.detect_scroll_direction(event)
            new_val = HistogramControlsModule.clamp_min(
                float(min_var.get()), step, direction_down,
                min_limit, float(max_var.get()),
                log_mode=log_mode,
            )
            min_var.set(f"{new_val:.1f}")
            self._schedule_render()
        except Exception:
            pass

    def _on_max_scroll(
        self, event, max_var: tk.StringVar, min_var: tk.StringVar,
        min_limit: float, max_limit: float, step: float = 0.5,
        log_mode: bool = False,
    ) -> None:
        """Handle scroll wheel on a max-value entry.

        Scroll direction is detected by ``HistogramControlsModule``; arithmetic
        is delegated to ``HistogramControlsModule.clamp_max``.
        """
        try:
            direction_down = HistogramControlsModule.detect_scroll_direction(event)
            new_val = HistogramControlsModule.clamp_max(
                float(max_var.get()), step, direction_down,
                float(min_var.get()), max_limit,
                log_mode=log_mode,
            )
            max_var.set(f"{new_val:.1f}")
            self._schedule_render()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Render scheduling
    # ------------------------------------------------------------------

    def _schedule_render(self, delay: int = 150) -> None:
        """Schedule a debounced render after any control change."""
        try:
            app = getattr(self, "_app", None)
            if not app:
                return
            if self._pending_after.get("id") is not None:
                try:
                    app.after_cancel(self._pending_after["id"])
                except Exception:
                    pass
            self._pending_after["id"] = app.after(
                delay, lambda: self.render_preview(self._current_obj)
            )
        except Exception:
            pass

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
        self._fit_listbox: tk.Listbox | None = None
        self._fit_listbox_ids: list[int] = []
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

        # Preview area — horizontal PanedWindow: histogram (dominant) | fit panel (compact)
        preview_frame = ttk.PanedWindow(content_frame, orient=tk.HORIZONTAL)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        hist_area = ttk.Frame(preview_frame)
        preview_frame.add(hist_area, weight=3)
        preview_label = tk.Label(hist_area, bg="white")
        preview_label.pack(fill=tk.BOTH, expand=True)

        fit_area = ttk.Frame(preview_frame)
        preview_frame.add(fit_area, weight=1)

        # Fit preview fills the right panel — fit results are rendered as a
        # compact TPaveText overlay on the TCanvas itself (lower-right corner).
        fit_preview_label = tk.Label(fit_area, text="No fit yet", bg="white", fg="gray")
        fit_preview_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._fit_result_text = None
        self._fit_preview_label = fit_preview_label
        self._preview_label = preview_label
        self._current_obj = obj

        # Re-render on window resize only — not on every internal widget repaint.
        # Guard conditions:
        #   1. Only react when the top-level window itself is the source of the
        #      Configure event (child-widget repaints also fire this binding, e.g.
        #      the PanedWindow sash moving after fit results are written, or the
        #      fit preview label receiving a new image).
        #   2. Only re-render when the outer dimensions actually changed (avoids
        #      repeated renders when the window is merely focused/moved).
        #   3. Route through _schedule_render() so concurrent renders are properly
        #      debounced and cancelled via after_cancel.
        try:
            toplevel = preview_label.winfo_toplevel()
            _last_size: list[tuple[int, int]] = [(0, 0)]
            def _on_config(event: tk.Event) -> None:  # type: ignore[type-arg]
                try:
                    if event.widget is not toplevel:
                        return
                    new_size = (toplevel.winfo_width(), toplevel.winfo_height())
                    if new_size == _last_size[0]:
                        return
                    _last_size[0] = new_size
                    self._schedule_render()
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

        # Single save button — dedicated row, right-aligned, clearly visible
        save_bar = ttk.Frame(controls_frame)
        save_bar.pack(fill=tk.X, padx=4, pady=(2, 2))
        ttk.Button(
            save_bar, text="Save…",
            command=lambda: self._open_save_dialog(),
        ).pack(side=tk.RIGHT)

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
        ttk.Button(
            peak_controls, text="Fit All",
            command=lambda: self._fit_add_all_peaks(),
        ).pack(side=tk.LEFT, padx=(0, 2))

        try:
            app.after(200, lambda: self._peak_finder._find_peaks(app))
        except Exception:
            pass

    def _build_peak_search_options(self, peak_panel: ttk.Frame, app) -> None:
        """Removed — search configuration was unintuitive. Preserved as a no-op
        so any subclass or external caller does not raise AttributeError."""

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

        # Listbox for fit selection with scrollbar
        lb_frame = ttk.Frame(fit_panel)
        lb_frame.pack(fill=tk.X)
        self._fit_listbox = tk.Listbox(
            lb_frame, height=4, selectmode=tk.SINGLE, exportselection=False, width=22,
        )
        lb_sb = ttk.Scrollbar(lb_frame, orient="vertical", command=self._fit_listbox.yview)
        self._fit_listbox.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._fit_listbox.pack(fill=tk.BOTH, expand=True)
        self._fit_listbox.bind("<<ListboxSelect>>", lambda e: self._on_fit_listbox_changed())

        # Add / Remove buttons
        btn_row = ttk.Frame(fit_panel)
        btn_row.pack(fill=tk.X, pady=(2, 0))
        ttk.Button(btn_row, text="+ Fit", command=self._fit_add).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="Remove", command=self._fit_remove_selected).pack(side=tk.LEFT)

        # Container that shows the active fit's compact controls
        self._fit_container = ttk.Frame(fit_panel)
        self._fit_container.pack(fill=tk.X, pady=(2, 0))

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

        # Pre-fill seed parameters when energy is known
        if energy is not None and self._fit_listbox is not None:
            self._fit_prefill_params(fit_id, ui_state, energy, width)

        if self._fit_listbox is not None:
            self._fit_listbox.insert(tk.END, fit_name)
            self._fit_listbox_ids.append(fit_id)
            idx = len(self._fit_listbox_ids) - 1
            self._fit_listbox.selection_clear(0, tk.END)
            self._fit_listbox.selection_set(idx)
            self._fit_listbox.see(idx)

        self._fit_show_frame(fit_id)

    def _fit_add_all_peaks(self) -> None:
        """Create a fit for every detected peak using an estimated width."""
        pf = getattr(self, "_peak_finder", None)
        if pf is None or self._fit_module is None:
            return
        for peak in list(pf.peaks):
            energy = peak.get("energy")
            if energy is None:
                continue
            width = self._fit_module.estimate_peak_width(energy)
            self._fit_add(energy=energy, width=width)

    def _fit_prefill_params(
        self,
        fit_id: int,
        ui_state: dict,
        energy: float,
        width: float | None,
    ) -> None:
        """Pre-fill parameter entries with seed values from *FitFeature*."""
        if self._fit_module is None:
            return
        fit_func = ui_state["fit_func_var"].get()
        hist_clone = self._fit_module.current_hist_clone or self._fit_module.current_hist
        width_val = (
            width if (width is not None and width > 0)
            else self._fit_module.estimate_peak_width(energy)
        )
        xmin, xmax = FitFeature.get_fit_range(energy, width_val)
        if xmin is None:
            xmin, xmax = energy - width_val / 2.0, energy + width_val / 2.0
        params = FitFeature.default_fit_params(
            fit_func, hist_clone, energy, width_val, xmin, xmax
        )
        for i, var in enumerate(ui_state["param_entries"]):
            if i < len(params):
                var.set(f"{params[i]:.4g}")

    def _fit_remove_selected(self) -> None:
        """Remove the fit currently selected in the listbox."""
        if self._fit_listbox is None:
            return
        sel = self._fit_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._fit_listbox_ids):
            return
        fit_id = self._fit_listbox_ids[idx]

        # Clean up UI state first so a mid-cleanup error does not leave the
        # listbox and _fit_module out of sync.
        if fit_id in self._fit_frames:
            try:
                self._fit_frames[fit_id].destroy()
            except Exception:
                pass
            del self._fit_frames[fit_id]
        if fit_id in self._fit_ui_states:
            del self._fit_ui_states[fit_id]

        self._fit_listbox.delete(idx)
        del self._fit_listbox_ids[idx]

        # Remove from domain module after the UI is already consistent
        if self._fit_module is not None:
            self._fit_module.remove_fit(fit_id)

        new_count = self._fit_listbox.size()
        if new_count > 0:
            new_idx = min(idx, new_count - 1)
            self._fit_listbox.selection_set(new_idx)
            self._fit_show_frame(self._fit_listbox_ids[new_idx])

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

        ttk.Label(row0, text="E:").pack(side=tk.LEFT, padx=(0, 1))
        ttk.Entry(row0, textvariable=ui_state["energy_var"], width=6).pack(
            side=tk.LEFT, padx=(0, 3)
        )
        ttk.Label(row0, text="W:").pack(side=tk.LEFT, padx=(0, 1))
        ttk.Entry(row0, textvariable=ui_state["width_var"], width=5).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(
            row0, text="Fit",
            command=lambda fid=fit_id: self._fit_trigger(fid),
        ).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(
            row0, text="Refit",
            command=lambda fid=fit_id: self._fit_trigger(fid),
        ).pack(side=tk.LEFT)

        # Parameters frame
        params_frame = ttk.LabelFrame(card, text="Initial Parameters (gaus)")
        params_frame.pack(fill=tk.X, pady=(2, 1))
        ui_state["params_frame"] = params_frame
        self._fit_rebuild_params(ui_state, FitFeature.get_param_labels("gaus"))

        return ui_state

    def _fit_rebuild_params(self, ui_state: dict, param_names: list[str]) -> None:
        """Destroy and recreate parameter entry widgets in the params frame.

        Parameters are arranged in a 2-per-row grid so that even fit functions
        with many parameters (e.g. *2gaus+pol1* with 8) remain readable without
        a very wide horizontal scroll.
        """
        frame = ui_state["params_frame"]
        for w in frame.winfo_children():
            w.destroy()
        ui_state["param_entries"] = []
        ui_state["param_fixed_vars"] = []

        cols_per_row = 2
        for i, name in enumerate(param_names):
            grid_row = i // cols_per_row
            col_base = (i % cols_per_row) * 3
            ttk.Label(frame, text=f"{name}:").grid(
                row=grid_row, column=col_base, sticky="e", padx=(2, 1), pady=(1, 0)
            )
            var = tk.StringVar(value="")
            ttk.Entry(frame, textvariable=var, width=7).grid(
                row=grid_row, column=col_base + 1, sticky="w", padx=(0, 1), pady=(1, 0)
            )
            var.trace_add("write", lambda *_, us=ui_state: self._fit_schedule_refit(us))
            fixed_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text="Fix", variable=fixed_var).grid(
                row=grid_row, column=col_base + 2, sticky="w", padx=(0, 4), pady=(1, 0)
            )
            ui_state["param_entries"].append(var)
            ui_state["param_fixed_vars"].append(fixed_var)

    # ------------------------------------------------------------------
    # Fit event handlers
    # ------------------------------------------------------------------

    def _on_fit_listbox_changed(self) -> None:
        if self._fit_module is None or self._fit_listbox is None:
            return
        sel = self._fit_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._fit_listbox_ids):
            self._fit_show_frame(self._fit_listbox_ids[idx])

    def _fit_show_frame(self, fit_id: int) -> None:
        for frame in self._fit_frames.values():
            frame.pack_forget()
        if fit_id in self._fit_frames:
            self._fit_frames[fit_id].pack(fill=tk.X)
        # Sync listbox selection
        if self._fit_listbox is not None:
            try:
                idx = self._fit_listbox_ids.index(fit_id)
                self._fit_listbox.selection_clear(0, tk.END)
                self._fit_listbox.selection_set(idx)
                self._fit_listbox.see(idx)
            except (ValueError, AttributeError):
                pass
        # Update the preview canvas for the newly selected fit
        self._render_fit_preview(fit_id)

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

    def _render_fit_preview(self, fit_id: int) -> None:
        """Render (or re-render) the zoomed fit preview for *fit_id*.

        Used both when a fit completes and when the user selects a fit in the
        listbox so the preview always tracks the selected fit.
        """
        if self._fit_module is None:
            return
        state = self._fit_module.get_fit_state(fit_id)
        if state is None:
            return

        fit_func     = state.get("fit_func", "gaus")
        energy       = state.get("energy")
        width        = state.get("width") or 20.0
        cached       = state.get("cached_results")
        fit_func_obj = state.get("fit_func_obj")   # TF1 specific to this fit

        pavetext = None
        if cached and "error" not in cached:
            pavetext = FitFeature.format_fit_results_short(fit_func, cached)

        pm = getattr(self, "_preview_manager", None)
        fit_label = self._fit_preview_label
        if pm is None or fit_label is None:
            return

        root  = self._fit_module.get_root_module(getattr(self, "_app", None))
        clone = self._fit_module.current_hist_clone
        if root is None or clone is None:
            return

        try:
            preview_opts: dict = {}
            if energy is not None:
                try:
                    xmin = float(energy) - float(width) / 2.0
                    xmax = float(energy) + float(width) / 2.0
                    preview_opts["xmin"] = xmin
                    preview_opts["xmax"] = xmax
                except Exception:
                    pass
            if pavetext:
                preview_opts["pavetext"] = pavetext
            # Pass the per-fit TF1 so the renderer draws only this curve.
            if fit_func_obj is not None:
                preview_opts["fit_func_obj"] = fit_func_obj
            pm.render_into_label_async(
                root, clone, fit_label, options=preview_opts, delay_ms=80
            )
        except Exception as exc:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Fit preview render failed",
                context="HistogramPreviewRenderer._render_fit_preview",
                exception=exc,
            )

    def _on_fit_completed(self, fit_id: int, cached: dict) -> None:
        """Called by FitModule after a fit completes."""
        self._render_fit_preview(fit_id)

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

        png_var        = tk.BooleanVar(value=True)
        pdf_var        = tk.BooleanVar(value=True)
        csv_peaks_var  = tk.BooleanVar(value=False)
        csv_fits_var   = tk.BooleanVar(value=False)
        json_peaks_var = tk.BooleanVar(value=False)
        json_fits_var  = tk.BooleanVar(value=False)
        fit_report_var = tk.BooleanVar(value=False)

        tk.Checkbutton(fmt_frame, text="PNG (preview)",    variable=png_var).pack(anchor="w")
        tk.Checkbutton(fmt_frame, text="PDF (preview)",    variable=pdf_var).pack(anchor="w")

        # CSV row — peaks (independent) and fits (forces peaks on)
        csv_row = tk.Frame(fmt_frame)
        csv_row.pack(anchor="w")
        csv_peaks_cb = tk.Checkbutton(csv_row, text="CSV (peaks)",
                                      variable=csv_peaks_var)
        csv_peaks_cb.pack(side=tk.LEFT)
        tk.Checkbutton(
            csv_row, text="+ fit results",
            variable=csv_fits_var,
            command=lambda: _on_fits_toggle(
                csv_fits_var, csv_peaks_var, csv_peaks_cb
            ),
        ).pack(side=tk.LEFT, padx=(6, 0))

        # JSON row — peaks (independent) and fits (forces peaks on)
        json_row = tk.Frame(fmt_frame)
        json_row.pack(anchor="w")
        json_peaks_cb = tk.Checkbutton(json_row, text="JSON (peaks)",
                                       variable=json_peaks_var)
        json_peaks_cb.pack(side=tk.LEFT)
        tk.Checkbutton(
            json_row, text="+ fit results",
            variable=json_fits_var,
            command=lambda: _on_fits_toggle(
                json_fits_var, json_peaks_var, json_peaks_cb
            ),
        ).pack(side=tk.LEFT, padx=(6, 0))

        tk.Checkbutton(fmt_frame, text="PDF (fit report)", variable=fit_report_var).pack(anchor="w")

        def _on_fits_toggle(
            fits_var: tk.BooleanVar,
            peaks_var: tk.BooleanVar,
            peaks_cb: tk.Checkbutton,
        ) -> None:
            """When '+ fit results' is checked, force peaks on and lock it."""
            if fits_var.get():
                peaks_var.set(True)
                peaks_cb.configure(state="disabled")
            else:
                peaks_cb.configure(state="normal")

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
            if not any((png_var.get(), pdf_var.get(),
                        csv_peaks_var.get(), json_peaks_var.get(),
                        fit_report_var.get())):
                messagebox.showerror("Save", "Select at least one output format.", parent=dialog)
                return

            # Assemble current render options from axis controls
            _pf_save = getattr(self, "_peak_finder", None)
            _peaks_save = getattr(_pf_save, "peaks", [])
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
                peak_energies=[p["energy"] for p in _peaks_save if p.get("source") == "automatic"],
                manual_peak_energies=[p["energy"] for p in _peaks_save if p.get("source") == "manual"],
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

            if csv_peaks_var.get():
                if not peaks:
                    messagebox.showwarning("Save", "No peaks to export as CSV.", parent=dialog)
                else:
                    try:
                        csv_path = os.path.join(directory, f"{name}_peaks.csv")
                        # Pass fit_states only when the user explicitly requested fits
                        save_mgr.export_peaks_csv(
                            peaks, name, csv_path,
                            fit_states=fit_states if csv_fits_var.get() else None,
                        )
                        saved.append(csv_path)
                    except Exception as exc:
                        messagebox.showerror("Save", f"CSV export failed:\n{exc}", parent=dialog)
                        return

            if json_peaks_var.get():
                if not peaks:
                    messagebox.showwarning("Save", "No peaks to export as JSON.", parent=dialog)
                else:
                    try:
                        json_path = os.path.join(directory, f"{name}_peaks.json")
                        save_mgr.export_peaks_json(
                            peaks, name, json_path,
                            fit_states=fit_states if json_fits_var.get() else None,
                        )
                        saved.append(json_path)
                    except Exception as exc:
                        messagebox.showerror("Save", f"JSON export failed:\n{exc}", parent=dialog)
                        return

            if fit_report_var.get():
                has_fits = (
                    fit_states is not None
                    and any(s.get("has_fit") for s in fit_states.values())
                )
                if not has_fits:
                    messagebox.showwarning(
                        "Save", "No completed fits to include in the report.", parent=dialog
                    )
                else:
                    try:
                        report_path = save_mgr.export_fit_report_pdf(
                            root, obj, fit_states, directory, name
                        )
                        if report_path:
                            saved.append(report_path)
                    except Exception as exc:
                        messagebox.showerror(
                            "Save", f"Fit report export failed:\n{exc}", parent=dialog
                        )
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
        _pf = getattr(self, "_peak_finder", None)
        _peaks = getattr(_pf, "peaks", [])
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
            peak_energies=[p["energy"] for p in _peaks if p.get("source") == "automatic"],
            manual_peak_energies=[p["energy"] for p in _peaks if p.get("source") == "manual"],
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

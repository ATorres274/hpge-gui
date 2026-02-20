from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from modules.histogram_controls_module import HistogramControlsModule
from modules.peak_manager import PeakFinderModule
from modules.preview_manager import HistogramRenderer
from modules.error_dispatcher import get_dispatcher, ErrorLevel

class HistogramTab:
    """Histogram tab view - manages multiple histogram previews and controls.

    This tab creates a simple container for each opened histogram
    and delegates preview UI creation to `HistogramPreviewRenderer`. It intentionally
    keeps behavior minimal so modules can be re-attached incrementally.
    
    Callbacks (provided by app for visibility orchestration):
    - on_histogram_selected(tab_key: str) - called when user selects a histogram
    - on_histogram_closed(remaining_count: int) - called when histogram is closed
    """

    def __init__(self, app, hist_container: ttk.Frame, 
                 on_histogram_selected=None, on_histogram_closed=None, on_histogram_opened=None):
        self.app = app
        self._hist_container = hist_container
        self._dispatcher = get_dispatcher()
        
        # Callbacks from app for orchestration (not hooks, formal interface)
        self._on_histogram_selected = on_histogram_selected
        self._on_histogram_closed = on_histogram_closed
        self._on_histogram_opened = on_histogram_opened

        # Shared preview renderer for this manager
        try:
            self._preview_manager = HistogramRenderer()
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to initialize HistogramRenderer",
                context="HistogramTab",
                exception=e
            )
            self._preview_manager = None

        # store (container, renderer, obj) tuples for each open histogram
        self._hist_tabs: dict[str, tuple[ttk.Frame, object, object]] = {}
        self._open_histograms: list[tuple[str, str, str]] = []
        self._current_histogram_key: str | None = None

    @property
    def current_histogram_key(self) -> str | None:
        """Return the key of the currently displayed histogram, or None."""
        return self._current_histogram_key

    def open_histogram(self, obj, root_path: str, path: str) -> None:
        tab_key = f"{root_path}:{path}"
        hist_name = getattr(obj, 'GetName', lambda: 'hist')()
        file_name = os.path.basename(root_path) or root_path
        display_name = f"{file_name} / {hist_name}"

        if tab_key in self._hist_tabs:
            self.show_histogram(tab_key)
            # Notify app of selection even if histogram already exists
            if self._on_histogram_selected and callable(self._on_histogram_selected):
                try:
                    self._on_histogram_selected(tab_key)
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to notify app of histogram selection",
                        context="HistogramTab.open_histogram",
                        exception=e
                    )
            return

        container = ttk.Frame(self._hist_container)
        renderer = HistogramPreviewRenderer()
        # give renderer access to the preview manager so it can render into
        # its local preview label.
        try:
            renderer._preview_manager = self._preview_manager
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to assign preview manager to renderer",
                context="HistogramTab.open_histogram",
                exception=e
            )
            renderer._preview_manager = None

        renderer.build_histogram_tab(self.app, container, obj, root_path, path)
        # Render a preview for this histogram via the preview manager.
        try:
            renderer.render_preview(obj)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to render histogram preview",
                context="HistogramTab.open_histogram",
                exception=e
            )

        # store obj so we can re-render when the tab is shown
        self._hist_tabs[tab_key] = (container, renderer, obj)
        self._open_histograms.append((tab_key, display_name, root_path))
        
        # Notify app of new histogram
        if self._on_histogram_opened and callable(self._on_histogram_opened):
            try:
                self._on_histogram_opened([(k, n) for k, n, _ in self._open_histograms])
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram opened",
                    context="HistogramTab.open_histogram",
                    exception=e
                )
        
        self.show_histogram(tab_key)
        
        # Notify app of selection
        if self._on_histogram_selected and callable(self._on_histogram_selected):
            try:
                self._on_histogram_selected(tab_key)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram selection",
                    context="HistogramTab.open_histogram",
                    exception=e
                )

    def show_histogram(self, tab_key: str) -> None:
        if tab_key not in self._hist_tabs:
            return
        # hide others (unconditionally, even if not currently mapped, so they don't
        # reappear when _hist_container is re-packed after returning from the browser)
        for k, v in self._hist_tabs.items():
            c = v[0]
            if k != tab_key:
                c.pack_forget()

        container, renderer, obj = self._hist_tabs[tab_key]
        if not self._hist_container.winfo_ismapped():
            try:
                self._hist_container.pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to pack histogram container",
                    context="HistogramTab.show_histogram",
                    exception=e
                )
        if not container.winfo_ismapped():
            try:
                container.pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to pack histogram tab container",
                    context="HistogramTab.show_histogram",
                    exception=e
                )

        self._current_histogram_key = tab_key

        # Render preview if renderer is ready
        try:
            renderer.render_preview(obj)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to render preview when showing histogram",
                context="HistogramTab.show_histogram",
                exception=e
            )

    def hide_all_histograms(self) -> None:
        """Hide all open histogram containers and clear current selection."""
        try:
            for c, renderer, obj in self._hist_tabs.values():
                try:
                    if c.winfo_ismapped():
                        c.pack_forget()
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to hide histogram container",
                        context="HistogramTab.hide_all_histograms",
                        exception=e
                    )
            try:
                if self._hist_container.winfo_ismapped():
                    self._hist_container.pack_forget()
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to hide histogram tab container",
                    context="HistogramTab.hide_all_histograms",
                    exception=e
                )
            self._current_histogram_key = None
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to hide all histograms",
                context="HistogramTab.hide_all_histograms",
                exception=e
            )

    def on_histogram_selected(self) -> None:
        """User selected a histogram from within the manager.
        
        Notify the app via callback so it can orchestrate visibility.
        """
        # Notify app of selection (app orchestrates visibility)
        if self._on_histogram_selected and callable(self._on_histogram_selected):
            try:
                # Get the selected histogram key from _open_histograms
                # This is called from app when combo changes
                if hasattr(self, '_pending_selection'):
                    tab_key = self._pending_selection
                    delattr(self, '_pending_selection')
                    self._on_histogram_selected(tab_key)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram selection",
                    context="HistogramTab.on_histogram_selected",
                    exception=e
                )

    def close_current_histogram(self) -> None:
        """Close the currently displayed histogram."""
        if self._current_histogram_key and self._current_histogram_key in self._hist_tabs:
            self.remove_histogram(self._current_histogram_key)

    def remove_histogram(self, tab_key: str) -> None:
        """Remove a histogram from the tab."""
        if tab_key not in self._hist_tabs:
            return
        
        try:
            # Remember the index of the histogram being closed before removing it
            closed_idx = next(
                (i for i, (k, _, _) in enumerate(self._open_histograms) if k == tab_key),
                -1,
            )

            # Remove from tracking
            container, renderer, obj = self._hist_tabs[tab_key]
            # Unpack the container explicitly before removing from tracking so that
            # hide_all_histograms (called below when closing the current histogram)
            # does not leave this container packed after it is no longer tracked.
            try:
                container.pack_forget()
            except Exception:
                pass
            del self._hist_tabs[tab_key]
            
            # Remove from dropdown list
            self._open_histograms = [(k, n, p) for k, n, p in self._open_histograms if k != tab_key]
            
            # Update dropdown via app callback
            if hasattr(self, '_app') and hasattr(self._app, 'update_histogram_dropdown'):
                try:
                    self._app.update_histogram_dropdown([(k, n) for k, n, _ in self._open_histograms])
                except Exception:
                    pass
            
            # Clear as current if it was
            if self._current_histogram_key == tab_key:
                self._current_histogram_key = None
                if self._open_histograms:
                    # Show the next histogram in sequence (or the previous one if the
                    # closed histogram was the last entry in the list).
                    next_idx = min(closed_idx, len(self._open_histograms) - 1)
                    next_key = self._open_histograms[next_idx][0]
                    self.show_histogram(next_key)
                else:
                    self.hide_all_histograms()

            # Notify app of remaining count via callback
            remaining = len(self._hist_tabs)
            if self._on_histogram_closed and callable(self._on_histogram_closed):
                try:
                    self._on_histogram_closed(remaining)
                except Exception:
                    pass
        except Exception:
            pass

    def remove_histogram_by_index(self, idx: int) -> None:
        """Remove a histogram by its dropdown index."""
        if idx < 0 or idx >= len(self._open_histograms):
            return
        tab_key, _, _ = self._open_histograms[idx]
        self.remove_histogram(tab_key)


class HistogramPreviewRenderer:
    """Renders individual histogram preview with interactive controls.
    
    Handles rendering, axis controls, range adjustments, and log scale toggles
    for a single histogram preview within the HistogramTab.
    """

    def __init__(self) -> None:
        self._pending_after: dict = {"id": None}

    def build_histogram_tab(self, app, parent_container: ttk.Frame, obj, root_path: str, path: str) -> ttk.Frame:
        # keep a reference to the app (used for rendering via HistogramRenderer)
        try:
            self._app = app
        except Exception:
            self._app = None

        main_frame = ttk.Frame(parent_container)
        # add a minimal outer margin so the panel background barely shows
        main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Content area: controls (top 1/3) and histogram preview (bottom 2/3).
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))

        # Use grid so we can give the controls 1x weight and histogram 2x weight
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)  # controls area (top)
        # Give controls and preview equal weight so preview is at most half
        content_frame.rowconfigure(1, weight=1)  # histogram preview area (bottom)

        # Controls area (top third)
        controls_frame = ttk.Frame(content_frame)
        controls_frame.grid(row=0, column=0, sticky="nsew")

        top_sep = ttk.Separator(controls_frame, orient="horizontal")
        top_sep.pack(fill=tk.X, padx=4, pady=(2, 2))

        # Middle control area (between separators)
        middle_bar = ttk.Frame(controls_frame)
        middle_bar.pack(fill=tk.X, padx=4, pady=(0, 0))

        # Histogram preview area (bottom two-thirds)
        preview_frame = ttk.Frame(content_frame)
        preview_frame.grid(row=1, column=0, sticky="nsew", pady=(2, 2))
        # use a Label so `HistogramRenderer` can place a Tk PhotoImage into it
        preview_label = tk.Label(preview_frame, bg="white")
        # keep a minimal inner margin so the label barely clears axis/title
        preview_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # store preview label and current object on renderer for later rendering
        self._preview_label = preview_label
        # store the object so resize events can re-render the same histogram
        self._current_obj = obj

        # Recompute preview size when the main window resizes and re-render.
        try:
            toplevel = preview_label.winfo_toplevel()
            def _on_config(event):
                try:
                    # choose preference based on window aspect ratio
                    w = event.width
                    h = event.height
                    prefer_width = (w >= h)
                    # call render_preview with stored object
                    try:
                        self.render_preview(self._current_obj)
                    except Exception:
                        pass
                except Exception:
                    pass

            toplevel.bind("<Configure>", _on_config)
        except Exception:
            pass

        # --- Preview controls: axis ranges, title, markers, peaks ---
        try:
            defaults = HistogramControlsModule.compute_defaults(obj)
            axis_controls = ttk.Frame(middle_bar)
            axis_controls.pack(side=tk.LEFT, anchor="nw", padx=2, pady=(0, 0))
            self._build_axis_controls(axis_controls, app, defaults)
            # --- Peak finder panel (right of axis controls) ---
            self._build_peak_panel(middle_bar, app, obj)
        except Exception:
            pass

        # Add bottom separator line
        bottom_sep = ttk.Separator(controls_frame, orient="horizontal")
        bottom_sep.pack(fill=tk.X, padx=4, pady=(2, 0))

        return main_frame

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
        # Y max has no hard upper cap — ROOT allows the range to exceed data max
        _Y_MAX_LIMIT = float("inf")

        # --- Row 0: Title ---
        ttk.Label(axis_controls, text="Title:").grid(
            row=0, column=0, sticky="e", padx=(2, 2), pady=(2, 2))
        ttk.Entry(axis_controls, textvariable=self._title_var, width=30).grid(
            row=0, column=1, columnspan=3, padx=(0, 4), pady=(2, 2))

        # --- Row 1: X range ---
        ttk.Label(axis_controls, text="X:").grid(
            row=1, column=0, sticky="e", padx=(2, 2), pady=(2, 1))
        x_min_text = ttk.Entry(axis_controls, textvariable=self._xmin_var, width=8)
        x_min_text.grid(row=1, column=1, padx=(0, 2), pady=(2, 1))
        ttk.Label(axis_controls, text="to").grid(row=1, column=2, padx=2, pady=(2, 1))
        x_max_text = ttk.Entry(axis_controls, textvariable=self._xmax_var, width=8)
        x_max_text.grid(row=1, column=3, padx=(0, 4), pady=(2, 1))
        ttk.Checkbutton(
            axis_controls, text="Log X", variable=self._logx_var,
            command=lambda: self._schedule_render(),
        ).grid(row=1, column=4, padx=(0, 2), pady=(2, 1))

        def _format_xmin(event=None):
            result = HistogramControlsModule.validate_min(
                self._xmin_var.get(), self._xmax_var.get(),
                hard_min=self._x_hard_min)
            if result is not None:
                self._xmin_var.set(result)
            self._schedule_render()

        def _format_xmax(event=None):
            result = HistogramControlsModule.validate_max(
                self._xmax_var.get(), self._xmin_var.get(),
                hard_max=self._x_hard_max)
            if result is not None:
                self._xmax_var.set(result)
            self._schedule_render()

        x_min_text.bind("<FocusOut>", _format_xmin)
        x_min_text.bind("<Return>",   _format_xmin)
        x_min_text.bind("<MouseWheel>", lambda e: self._on_min_scroll(
            e, self._xmin_var, self._xmax_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))
        x_min_text.bind("<Button-4>", lambda e: self._on_min_scroll(
            e, self._xmin_var, self._xmax_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))
        x_min_text.bind("<Button-5>", lambda e: self._on_min_scroll(
            e, self._xmin_var, self._xmax_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))
        x_max_text.bind("<FocusOut>", _format_xmax)
        x_max_text.bind("<Return>",   _format_xmax)
        x_max_text.bind("<MouseWheel>", lambda e: self._on_max_scroll(
            e, self._xmax_var, self._xmin_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))
        x_max_text.bind("<Button-4>", lambda e: self._on_max_scroll(
            e, self._xmax_var, self._xmin_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))
        x_max_text.bind("<Button-5>", lambda e: self._on_max_scroll(
            e, self._xmax_var, self._xmin_var,
            self._x_hard_min, self._x_hard_max, x_scroll_step,
            log_mode=self._logx_var.get()))

        # --- Row 2: X label ---
        ttk.Label(axis_controls, text="X label:").grid(
            row=2, column=0, sticky="e", padx=(2, 2), pady=(1, 2))
        ttk.Entry(axis_controls, textvariable=self._xlabel_var, width=30).grid(
            row=2, column=1, columnspan=3, padx=(0, 4), pady=(1, 2))

        # --- Row 3: Y range ---
        ttk.Label(axis_controls, text="Y:").grid(
            row=3, column=0, sticky="e", padx=(2, 2), pady=(2, 1))
        y_min_text = ttk.Entry(axis_controls, textvariable=self._ymin_var, width=8)
        y_min_text.grid(row=3, column=1, padx=(0, 2), pady=(2, 1))
        ttk.Label(axis_controls, text="to").grid(row=3, column=2, padx=2, pady=(2, 1))
        y_max_text = ttk.Entry(axis_controls, textvariable=self._ymax_var, width=8)
        y_max_text.grid(row=3, column=3, padx=(0, 4), pady=(2, 1))
        ttk.Checkbutton(
            axis_controls, text="Log Y", variable=self._logy_var,
            command=lambda: self._schedule_render(),
        ).grid(row=3, column=4, padx=(0, 2), pady=(2, 1))

        def _format_ymin(event=None):
            result = HistogramControlsModule.validate_min(
                self._ymin_var.get(), self._ymax_var.get(),
                hard_min=self._y_hard_min)
            if result is not None:
                self._ymin_var.set(result)
            self._schedule_render()

        def _format_ymax(event=None):
            # Y max has no hard upper cap
            result = HistogramControlsModule.validate_max(
                self._ymax_var.get(), self._ymin_var.get())
            if result is not None:
                self._ymax_var.set(result)
            self._schedule_render()

        y_min_text.bind("<FocusOut>", _format_ymin)
        y_min_text.bind("<Return>",   _format_ymin)
        y_min_text.bind("<MouseWheel>", lambda e: self._on_min_scroll(
            e, self._ymin_var, self._ymax_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))
        y_min_text.bind("<Button-4>", lambda e: self._on_min_scroll(
            e, self._ymin_var, self._ymax_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))
        y_min_text.bind("<Button-5>", lambda e: self._on_min_scroll(
            e, self._ymin_var, self._ymax_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))
        y_max_text.bind("<FocusOut>", _format_ymax)
        y_max_text.bind("<Return>",   _format_ymax)
        y_max_text.bind("<MouseWheel>", lambda e: self._on_max_scroll(
            e, self._ymax_var, self._ymin_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))
        y_max_text.bind("<Button-4>", lambda e: self._on_max_scroll(
            e, self._ymax_var, self._ymin_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))
        y_max_text.bind("<Button-5>", lambda e: self._on_max_scroll(
            e, self._ymax_var, self._ymin_var,
            self._y_hard_min, _Y_MAX_LIMIT, y_scroll_step,
            log_mode=self._logy_var.get()))

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

    def render_preview(self, obj) -> None:
        """Render a simple preview of the histogram onto the bottom canvas.

        This is intentionally lightweight: it attempts to read bin contents
        if `obj` behaves like a ROOT histogram (has `GetNbinsX` / `GetBinContent`).
        Otherwise a placeholder is drawn.
        """
        # Delegate sizing/rendering to the shared `HistogramRenderer` to
        # avoid duplicating geometry heuristics here.
        label = getattr(self, "_preview_label", None)
        pm = getattr(self, "_preview_manager", None)
        if label is None:
            return

        # Determine root/app window size and compute a target preview size
        # derived directly from the window size and panel proportions.
        root = None
        try:
            app = getattr(self, "_app", None)
            if app is not None:
                root = getattr(app, "ROOT", None)
        except Exception:
            root = None

        try:
            toplevel = label.winfo_toplevel()
            win_w = toplevel.winfo_width() or 800
            win_h = toplevel.winfo_height() or 600
        except Exception:
            win_w, win_h = 800, 600

        # Compute explicit target sizes via the module helper
        w, h = HistogramControlsModule.compute_preview_size(win_w, win_h)

        options = HistogramControlsModule.build_render_options(
            w, h,
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

    def _on_min_scroll(self, event, min_var, max_var, min_limit, max_limit, step=0.5, log_mode=False):
        """Handle scroll wheel on min value text box."""
        try:
            direction_down = (event.num == 5 or
                              (hasattr(event, "delta") and event.delta < 0))
            new_val = HistogramControlsModule.clamp_min(
                float(min_var.get()), step, direction_down,
                min_limit, float(max_var.get()),
                log_mode=log_mode,
            )
            min_var.set(f"{new_val:.1f}")
            self._schedule_render()
        except Exception:
            pass

    def _on_max_scroll(self, event, max_var, min_var, min_limit, max_limit, step=0.5, log_mode=False):
        """Handle scroll wheel on max value text box."""
        try:
            direction_down = (event.num == 5 or
                              (hasattr(event, "delta") and event.delta < 0))
            new_val = HistogramControlsModule.clamp_max(
                float(max_var.get()), step, direction_down,
                float(min_var.get()), max_limit,
                log_mode=log_mode,
            )
            max_var.set(f"{new_val:.1f}")
            self._schedule_render()
        except Exception:
            pass

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

        def _on_peak_double(event):
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

        def _show_peak_menu(event):
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

        peak_controls = ttk.Frame(peak_panel)
        peak_controls.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(peak_controls, text="Manual (keV):").pack(side=tk.LEFT, padx=(0, 2))
        manual_peak_var = tk.StringVar(value="")
        self._peak_finder._manual_peak_var = manual_peak_var
        manual_entry = ttk.Entry(peak_controls, textvariable=manual_peak_var, width=8)
        manual_entry.pack(side=tk.LEFT, padx=(0, 2))

        def _on_manual_enter(event):
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

        try:
            app.after(200, lambda: self._peak_finder._find_peaks(app))
        except Exception:
            pass

    def _get_root(self):
        # try to find a Tk root from the label widget
        try:
            label = getattr(self, "_preview_label", None)
            if label is None:
                return None
            return label.winfo_toplevel()
        except Exception:
            return None

    def _schedule_render(self, delay=150) -> None:
        """Schedule a debounced render after any change."""
        try:
            app = getattr(self, "_app", None)
            if not app:
                return
            if self._pending_after.get("id") is not None:
                try:
                    app.after_cancel(self._pending_after["id"])
                except Exception:
                    pass
            self._pending_after["id"] = app.after(delay, lambda: self.render_preview(self._current_obj))
        except Exception:
            pass



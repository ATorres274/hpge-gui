from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

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

            # Notify app of remaining count and updated list via callback
            remaining = len(self._hist_tabs)
            remaining_list = [(k, n) for k, n, _ in self._open_histograms]
            if self._on_histogram_closed and callable(self._on_histogram_closed):
                try:
                    self._on_histogram_closed(remaining, remaining_list)
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
        pass

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

        # --- Preview controls: double-sided sliders for X and Y ranges ---
        try:
            # create a compact controls area inside the existing controls_frame
            axis_controls = ttk.Frame(middle_bar)
            axis_controls.pack(fill=tk.X, padx=2, pady=(0, 0))

            # Determine defaults from histogram object when available
            xaxis = obj.GetXaxis() if hasattr(obj, "GetXaxis") else None
            yaxis = obj.GetYaxis() if hasattr(obj, "GetYaxis") else None
            try:
                x_min_default = float(xaxis.GetXmin()) if xaxis is not None else 0.1
                x_max_default = float(xaxis.GetXmax()) if xaxis is not None else x_min_default + 100.0
            except Exception:
                x_min_default = 0.1
                x_max_default = 100.0

            # Ensure x_min_default is never 0 or negative
            if x_min_default <= 0:
                x_min_default = 0.1

            try:
                y_min_default = float(obj.GetMinimum()) if hasattr(obj, 'GetMinimum') else 0.1
                y_max_default = float(obj.GetMaximum()) if hasattr(obj, 'GetMaximum') else y_min_default + 100.0
                # Scale max to be 1.2x higher
                y_max_default = y_max_default * 1.2
            except Exception:
                y_min_default = 0.1
                y_max_default = 120.0

            # Ensure y_min_default is never 0 or negative
            if y_min_default <= 0:
                y_min_default = 0.1

            # Variables for sliders (edge vars kept for compatibility)
            self._xmin_var = tk.DoubleVar(value=x_min_default)
            self._xmax_var = tk.DoubleVar(value=x_max_default)
            self._ymin_var = tk.DoubleVar(value=y_min_default)
            self._ymax_var = tk.DoubleVar(value=y_max_default)

            # Log scale toggles (log y enabled by default)
            self._logx_var = tk.BooleanVar(value=False)
            self._logy_var = tk.BooleanVar(value=True)

            # Axis label variables
            x_label_default = ""
            y_label_default = ""
            try:
                if xaxis is not None and hasattr(xaxis, 'GetTitle'):
                    x_label_default = str(xaxis.GetTitle())
            except Exception:
                pass
            try:
                if yaxis is not None and hasattr(yaxis, 'GetTitle'):
                    y_label_default = str(yaxis.GetTitle())
            except Exception:
                pass
            
            self._xlabel_var = tk.StringVar(value=x_label_default)
            self._ylabel_var = tk.StringVar(value=y_label_default)

            # Helper to schedule renders (debounced)
            self._pending_after = {"id": None}
            def _schedule_render(delay=150):
                try:
                    app = getattr(self, "_app", None)
                    if not app:
                        return
                    if self._pending_after["id"] is not None:
                        try:
                            app.after_cancel(self._pending_after["id"])
                        except Exception:
                            pass
                    self._pending_after["id"] = app.after(delay, lambda: self.render_preview(self._current_obj))
                except Exception:
                    pass

            # X range controls: center and width with text boxes
            xframe = ttk.Frame(axis_controls)
            xframe.pack(fill=tk.X, padx=0, pady=(1, 0))
            
            # X Label control
            x_label_label = ttk.Label(xframe, text="X label:", width=10)
            x_label_label.pack(side=tk.LEFT, padx=(2, 1))
            x_label_text = ttk.Entry(xframe, textvariable=self._xlabel_var, width=12)
            x_label_text.pack(side=tk.LEFT, padx=(0, 6))
            
            # Trigger render on X label change
            def _on_xlabel_change(*_):
                self._schedule_render()
            self._xlabel_var.trace_add("write", _on_xlabel_change)
            
            # X Min control
            x_min_label = ttk.Label(xframe, text="X min:", width=10)
            x_min_label.pack(side=tk.LEFT, padx=(0, 1))
            x_min_text = ttk.Entry(xframe, textvariable=self._xmin_var, width=8)
            x_min_text.pack(side=tk.LEFT, padx=(0, 4))
            
            # Format X min on focus out and validate
            def _format_xmin(event=None):
                try:
                    val = float(self._xmin_var.get())
                    # Ensure min is never 0 or negative
                    if val <= 0:
                        val = 0.1
                    # Ensure min doesn't cross max
                    xmax = float(self._xmax_var.get())
                    if val >= xmax:
                        val = xmax - 1.0
                    self._xmin_var.set(f"{val:.1f}")
                except (ValueError, tk.TclError):
                    pass
                self._schedule_render()
            x_min_text.bind("<FocusOut>", _format_xmin)
            x_min_text.bind("<MouseWheel>", lambda e: self._on_min_scroll(e, self._xmin_var, self._xmax_var, x_min_default, x_max_default * 2.5))
            x_min_text.bind("<Button-4>", lambda e: self._on_min_scroll(e, self._xmin_var, self._xmax_var, x_min_default, x_max_default * 2.5))
            x_min_text.bind("<Button-5>", lambda e: self._on_min_scroll(e, self._xmin_var, self._xmax_var, x_min_default, x_max_default * 2.5))
            
            # X Max control
            x_max_label = ttk.Label(xframe, text="X max:", width=8)
            x_max_label.pack(side=tk.LEFT, padx=(0, 1))
            x_max_text = ttk.Entry(xframe, textvariable=self._xmax_var, width=8)
            x_max_text.pack(side=tk.LEFT, padx=(0, 4))
            
            # Format X max on focus out and validate
            def _format_xmax(event=None):
                try:
                    val = float(self._xmax_var.get())
                    # Ensure max doesn't cross min
                    xmin = float(self._xmin_var.get())
                    if val <= xmin:
                        val = xmin + 1.0
                    self._xmax_var.set(f"{val:.1f}")
                except (ValueError, tk.TclError):
                    pass
                self._schedule_render()
            x_max_text.bind("<FocusOut>", _format_xmax)
            x_max_text.bind("<MouseWheel>", lambda e: self._on_max_scroll(e, self._xmax_var, self._xmin_var, x_min_default, x_max_default * 2.5))
            x_max_text.bind("<Button-4>", lambda e: self._on_max_scroll(e, self._xmax_var, self._xmin_var, x_min_default, x_max_default * 2.5))
            x_max_text.bind("<Button-5>", lambda e: self._on_max_scroll(e, self._xmax_var, self._xmin_var, x_min_default, x_max_default * 2.5))
            
            # Log X checkbox (aligned to the left near the entry boxes)
            logx_checkbox = ttk.Checkbutton(xframe, text="Log X", variable=self._logx_var, command=lambda: self._schedule_render())
            logx_checkbox.pack(side=tk.LEFT, padx=(4, 2))

            # Y range controls: center and width with text boxes
            yframe = ttk.Frame(axis_controls)
            yframe.pack(fill=tk.X, padx=0, pady=(1, 0))
            
            # Y Label control
            y_label_label = ttk.Label(yframe, text="Y label:", width=10)
            y_label_label.pack(side=tk.LEFT, padx=(2, 1))
            y_label_text = ttk.Entry(yframe, textvariable=self._ylabel_var, width=12)
            y_label_text.pack(side=tk.LEFT, padx=(0, 6))
            
            # Trigger render on Y label change
            def _on_ylabel_change(*_):
                self._schedule_render()
            self._ylabel_var.trace_add("write", _on_ylabel_change)
            
            # Y Min control
            y_min_label = ttk.Label(yframe, text="Y min:", width=10)
            y_min_label.pack(side=tk.LEFT, padx=(0, 1))
            y_min_text = ttk.Entry(yframe, textvariable=self._ymin_var, width=8)
            y_min_text.pack(side=tk.LEFT, padx=(0, 4))
            
            # Format Y min on focus out and validate
            def _format_ymin(event=None):
                try:
                    val = float(self._ymin_var.get())
                    # Ensure min is never 0 or negative
                    if val <= 0:
                        val = 0.1
                    # Ensure min doesn't cross max
                    ymax = float(self._ymax_var.get())
                    if val >= ymax:
                        val = ymax - 1.0
                    self._ymin_var.set(f"{val:.1f}")
                except (ValueError, tk.TclError):
                    pass
                self._schedule_render()
            y_min_text.bind("<FocusOut>", _format_ymin)
            y_min_text.bind("<MouseWheel>", lambda e: self._on_min_scroll(e, self._ymin_var, self._ymax_var, y_min_default, y_max_default * 2.5))
            y_min_text.bind("<Button-4>", lambda e: self._on_min_scroll(e, self._ymin_var, self._ymax_var, y_min_default, y_max_default * 2.5))
            y_min_text.bind("<Button-5>", lambda e: self._on_min_scroll(e, self._ymin_var, self._ymax_var, y_min_default, y_max_default * 2.5))
            
            # Y Max control
            y_max_label = ttk.Label(yframe, text="Y max:", width=8)
            y_max_label.pack(side=tk.LEFT, padx=(0, 1))
            y_max_text = ttk.Entry(yframe, textvariable=self._ymax_var, width=8)
            y_max_text.pack(side=tk.LEFT, padx=(0, 2))
            
            # Format Y max on focus out and validate
            def _format_ymax(event=None):
                try:
                    val = float(self._ymax_var.get())
                    # Ensure max doesn't cross min
                    ymin = float(self._ymin_var.get())
                    if val <= ymin:
                        val = ymin + 1.0
                    self._ymax_var.set(f"{val:.1f}")
                except (ValueError, tk.TclError):
                    pass
                self._schedule_render()
            y_max_text.bind("<FocusOut>", _format_ymax)
            y_max_text.bind("<MouseWheel>", lambda e: self._on_max_scroll(e, self._ymax_var, self._ymin_var, y_min_default, y_max_default * 2.5))
            y_max_text.bind("<Button-4>", lambda e: self._on_max_scroll(e, self._ymax_var, self._ymin_var, y_min_default, y_max_default * 2.5))
            y_max_text.bind("<Button-5>", lambda e: self._on_max_scroll(e, self._ymax_var, self._ymin_var, y_min_default, y_max_default * 2.5))

            # Log Y checkbox (aligned to the left near the entry boxes)
            logy_checkbox = ttk.Checkbutton(yframe, text="Log Y", variable=self._logy_var, command=lambda: self._schedule_render())
            logy_checkbox.pack(side=tk.LEFT, padx=(4, 2))

            # Update edge vars and schedule render on min/max changes
            def _on_min_max_change(*_):
                try:
                    xmin = float(self._xmin_var.get())
                    xmax = float(self._xmax_var.get())
                    ymin = float(self._ymin_var.get())
                    ymax = float(self._ymax_var.get())
                    
                    # Validate ranges
                    if xmin <= 0:
                        xmin = 0.1
                    if xmin >= xmax:
                        xmin = xmax - 1.0
                    if xmin <= 0:
                        xmin = 0.1
                    
                    if ymin <= 0:
                        ymin = 0.1
                    if ymin >= ymax:
                        ymin = ymax - 1.0
                    if ymin <= 0:
                        ymin = 0.1
                    
                    self._xmin_var.set(xmin)
                    self._xmax_var.set(xmax)
                    self._ymin_var.set(ymin)
                    self._ymax_var.set(ymax)
                except Exception:
                    pass
                _schedule_render()

            # Trace changes to min/max vars
            try:
                self._xmin_var.trace_add("write", _on_min_max_change)
                self._xmax_var.trace_add("write", _on_min_max_change)
                self._ymin_var.trace_add("write", _on_min_max_change)
                self._ymax_var.trace_add("write", _on_min_max_change)
            except Exception:
                pass
        except Exception:
            pass

        # Add bottom separator line
        bottom_sep = ttk.Separator(controls_frame, orient="horizontal")
        bottom_sep.pack(fill=tk.X, padx=4, pady=(2, 0))

        return main_frame

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

        # Compute explicit target sizes from the window: width uses ~80%
        # of window width, height uses at most 50% of window height.
        w = int(max(160, win_w * 0.8))
        h = int(max(120, win_h * 0.5))

        # Pass explicit target size and prefer height so vertical whitespace
        # is limited by the renderer. Also include any axis range controls
        # from the sliders so the previewer and renderer can honor zoom.
        options = {"target_width": int(w), "target_height": int(h), "priority": "height"}

        try:
            if hasattr(self, "_xmin_var") and hasattr(self, "_xmax_var"):
                options["xmin"] = float(self._xmin_var.get())
                options["xmax"] = float(self._xmax_var.get())
            if hasattr(self, "_ymin_var") and hasattr(self, "_ymax_var"):
                options["ymin"] = float(self._ymin_var.get())
                options["ymax"] = float(self._ymax_var.get())
            # Add log scale options
            if hasattr(self, "_logx_var"):
                options["logx"] = self._logx_var.get()
            if hasattr(self, "_logy_var"):
                options["logy"] = self._logy_var.get()
            # Add axis labels
            if hasattr(self, "_xlabel_var"):
                xlabel = self._xlabel_var.get()
                if xlabel:
                    options["xlabel"] = xlabel
            if hasattr(self, "_ylabel_var"):
                ylabel = self._ylabel_var.get()
                if ylabel:
                    options["ylabel"] = ylabel
        except Exception:
            pass

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

    def _on_min_scroll(self, event, min_var, max_var, min_limit, max_limit, step=0.5):
        """Handle scroll wheel on min value text box."""
        try:
            current = float(min_var.get())
            # Scroll up increases value, scroll down decreases
            if event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
                current -= step
            else:
                current += step
            
            # Clamp min to limits and ensure it doesn't exceed max
            current = max(min_limit, current)
            max_val = float(max_var.get())
            current = min(current, max_val - 1.0)
            # Ensure min is never 0 or negative
            if current <= 0:
                current = 0.1
            
            min_var.set(f"{current:.1f}")
            self._schedule_render()
        except Exception:
            pass

    def _on_max_scroll(self, event, max_var, min_var, min_limit, max_limit, step=0.5):
        """Handle scroll wheel on max value text box."""
        try:
            current = float(max_var.get())
            # Scroll up increases value, scroll down decreases
            if event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
                current -= step
            else:
                current += step
            
            # Clamp max to limits and ensure it doesn't go below min
            current = min(max_limit, current)
            min_val = float(min_var.get())
            current = max(current, min_val + 1.0)
            
            max_var.set(f"{current:.1f}")
            self._schedule_render()
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



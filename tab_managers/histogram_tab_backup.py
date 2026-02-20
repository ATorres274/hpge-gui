from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk, simpledialog

from modules.save_manager import AdvancedSaveDialog
from modules.peak_manager import PeakFinderModule
from modules.preview_manager import HistogramRenderer
from modules.save_manager import SaveManager
from modules.root_object_manager import RootObjectManager


class HistogramManager:
    """Manages histogram tab lifecycle - opening, showing, hiding, and closing histograms."""
    
    def __init__(self, app, hist_container: ttk.Frame, histogram_combo: ttk.Combobox, 
                 histogram_var: tk.StringVar, close_btn: ttk.Button):
        """Initialize histogram manager.
        """
        self.app = app
        self._hist_container = hist_container
        self._histogram_combo = histogram_combo
        self._histogram_var = histogram_var
        self._close_btn = close_btn

        # Histogram tracking
        self._hist_tabs: dict[str, tuple[ttk.Frame, ttk.Notebook, object]] = {}
        self._open_histograms: list[tuple[str, str, str]] = []  # (tab_key, display_name, root_path)
        self._current_histogram_key: str | None = None

        # Configure bindings
        self._histogram_combo.bind("<<ComboboxSelected>>", self.on_histogram_selected)
        self._close_btn.configure(command=self.close_current_histogram)
    def open_histogram(self, obj, root_path: str, path: str) -> None:
        """Open a histogram in a new tab.

        This mirrors the previous behavior: if the histogram is already open,
        show it; otherwise create a new tab and controller.
        """
        tab_key = f"{root_path}:{path}"
        display_name = f"{os.path.basename(root_path)} / {obj.GetName()}"

        # If already open, just show it
        if tab_key in self._hist_tabs:
            if hasattr(self.app, 'browser_manager') and root_path in self.app.browser_manager._open_root_files:
                self.app.browser_manager.root_file = self.app.browser_manager._open_root_files[root_path]
            self.show_histogram(tab_key)
            return

        # Create new histogram panel (no inner Notebook) so the histogram
        # occupies the main panel directly.
        group_container = ttk.Frame(self._hist_container)

        # Create histogram tab controller for this histogram using the
        # group container as the parent container.
        histogram_tab_controller = HistogramTabController()
        histogram_tab_controller.build_histogram_tab(
            self.app,
            group_container,
            obj,
            root_path,
            path,
        )

        # Store None for the inner_notebook slot to indicate we're using a
        # plain container rather than a Notebook tab.
        self._hist_tabs[tab_key] = (group_container, None, histogram_tab_controller)
        self._open_histograms.append((tab_key, display_name, root_path))
        self._update_dropdown()

        self.show_histogram(tab_key)
    def show_histogram(self, tab_key: str) -> None:
        """Show a specific histogram by its tab key.

        Handles hiding other open histograms and triggering any per-tab
        render/peak-find callbacks exposed by the tab controller.
        """
        if tab_key not in self._hist_tabs:
            return
        # Hide all other histograms
        for key, (container, _, _) in self._hist_tabs.items():
            if key != tab_key and container.winfo_ismapped():
                container.pack_forget()

        # Show the requested histogram
        container, inner_notebook, controller = self._hist_tabs[tab_key]
        if not self._hist_container.winfo_ismapped():
            self._hist_container.pack(fill=tk.BOTH, expand=True)
        if not container.winfo_ismapped():
            container.pack(fill=tk.BOTH, expand=True)

        self._current_histogram_key = tab_key
        if hasattr(self.app, 'browser_manager'):
            self.app.browser_manager.hide()

        # Update dropdown selection
        for idx, (key, _, _) in enumerate(self._open_histograms):
            if key == tab_key:
                self._histogram_combo.current(idx)
                break

        # If an inner notebook exists, select its first tab. Otherwise
        # nothing to select because the histogram occupies the main panel.
        if inner_notebook is not None and hasattr(inner_notebook, "tabs"):
            tabs = inner_notebook.tabs()
            if tabs:
                inner_notebook.select(tabs[0])

        # Trigger render and peak-find callbacks if provided by the
        # controller when this tab was built.
        try:
            if controller is not None:
                if hasattr(controller, "_schedule_render") and callable(controller._schedule_render):
                    controller._schedule_render()
                if hasattr(controller, "_trigger_find_peaks") and callable(controller._trigger_find_peaks):
                    controller._trigger_find_peaks()
        except Exception:
            pass
    def hide_all_histograms(self) -> None:
        """Hide all histogram containers."""
        for container, _, _ in self._hist_tabs.values():
            if container.winfo_ismapped():
                container.pack_forget()
        if self._hist_container.winfo_ismapped():
            self._hist_container.pack_forget()
        self._current_histogram_key = None
        if hasattr(self.app, 'browser_manager'):
            self.app.browser_manager.show()
    
    def focus(self) -> None:
        """Focus on histogram manager - show current histogram and hide browser."""
        # Hide browser when focusing histogram
        if hasattr(self.app, 'browser_manager'):
            self.app.browser_manager.hide()
        
        # Show current histogram if one is selected
        if self._current_histogram_key:
            self.show_histogram(self._current_histogram_key)
    
    def close_current_histogram(self) -> None:
        """Close the currently selected histogram."""
        if self._current_histogram_key is None:
            return
        
        tab_key = self._current_histogram_key
        if tab_key not in self._hist_tabs:
            return
        
        # Remove from data structures
        container, _, _ = self._hist_tabs.pop(tab_key)
        self._open_histograms = [(k, n, r) for k, n, r in self._open_histograms if k != tab_key]
        
        # Destroy the container
        container.destroy()
        
        # Update dropdown
        self._update_dropdown()
        
        # Show another histogram or browser
        if self._open_histograms:
            next_key, _, _ = self._open_histograms[0]
            self.show_histogram(next_key)
        else:
            self._current_histogram_key = None
            self.hide_all_histograms()
            self._histogram_var.set("")
    
    def on_histogram_selected(self, event) -> None:
        """Handle histogram selection from dropdown.
        
        Args:
            event: Tkinter event object
        """
        idx = self._histogram_combo.current()
        if idx < 0 or idx >= len(self._open_histograms):
            return
        tab_key, _, root_path = self._open_histograms[idx]
        
        if hasattr(self.app, 'browser_manager') and root_path in self.app.browser_manager._open_root_files:
            self.app.browser_manager.root_file = self.app.browser_manager._open_root_files[root_path]
        self.show_histogram(tab_key)
    
    def _update_dropdown(self) -> None:
        """Update the histogram dropdown with available histograms."""
        display_names = [name for _, name, _ in self._open_histograms]
        self._histogram_combo["values"] = display_names


class HistogramTabController:
    """Build and manage the histogram preview tab UI."""

    def __init__(self) -> None:
        """Initialize histogram tab controller with its own modules."""
        self._hist_renderer = HistogramRenderer()
        self._save_manager = SaveManager()
        self._root_object_manager = RootObjectManager()

    def build_histogram_tab(
        self,
        app,
        parent_container: ttk.Notebook,
        obj,
        root_path: str,
        path: str,
    ) -> ttk.Frame:
        """Build histogram panel with peak finder and fitting features.
        
        This method creates:
        1. Histogram display tab with rendering controls
        2. Peak finder feature integrated into histogram tab
        3. Fitting tab for peak analysis
        """
        # Create peak finder feature for this histogram
        peak_finder = PeakFinderModule()
        peak_finder.current_hist = obj
        peak_finder.parent_app = app
        peak_finder.host_notebook = hist_notebook
        
        main_frame = ttk.Frame(hist_notebook)
        hist_notebook.add(main_frame, text="Histogram")

        controls = ttk.Frame(main_frame)
        controls.pack(fill=tk.X, padx=4, pady=(2, 1))

        logx_var = tk.BooleanVar(value=False)
        logy_var = tk.BooleanVar(value=True)
        show_markers_var = tk.BooleanVar(value=True)

        current_title = obj.GetTitle() if hasattr(obj, "GetTitle") else ""
        xaxis = obj.GetXaxis() if hasattr(obj, "GetXaxis") else None
        yaxis = obj.GetYaxis() if hasattr(obj, "GetYaxis") else None
        current_xtitle = xaxis.GetTitle() if xaxis is not None else ""
        current_ytitle = yaxis.GetTitle() if yaxis is not None else ""

        title_var = tk.StringVar(value=current_title or "")
        xtitle_var = tk.StringVar(value=current_xtitle or "")
        ytitle_var = tk.StringVar(value=current_ytitle or "")

        # Create a compact frame for axis ranges
        axis_frame = ttk.Frame(controls)
        axis_frame.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        # Get default axis ranges from histogram for display and reset
        # Format them nicely - use int if whole number, otherwise use 1 decimal place
        def format_axis_value(val):
            if val is None:
                return ""
            if val == int(val):
                return str(int(val))
            return f"{val:.1f}"
        
        default_xmin = format_axis_value(xaxis.GetXmin()) if xaxis is not None else ""
        default_xmax = format_axis_value(xaxis.GetXmax()) if xaxis is not None else ""
        
        # For Y axis, get the actual minimum from histogram bins (not axis range which is often 0)
        if yaxis is not None and hasattr(obj, 'GetMinimum') and hasattr(obj, 'GetMaximum'):
            default_ymin = format_axis_value(obj.GetMinimum())
            default_ymax = format_axis_value(obj.GetMaximum())
        else:
            default_ymin = ""
            default_ymax = ""
        
        # Start with empty values so initial render uses histogram's natural ranges
        xmin_var = tk.StringVar(value="")
        xmax_var = tk.StringVar(value="")
        ymin_var = tk.StringVar(value="")
        ymax_var = tk.StringVar(value="")
        
        # X range
        ttk.Label(axis_frame, text="X:").grid(row=0, column=0, sticky="e", padx=(0, 2))
        ttk.Entry(axis_frame, textvariable=xmin_var, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(axis_frame, text="to").grid(row=0, column=2, sticky="w", padx=2)
        ttk.Entry(axis_frame, textvariable=xmax_var, width=8).grid(row=0, column=3, sticky="w")
        
        # X Title
        ttk.Label(axis_frame, text="X Title:").grid(row=1, column=0, sticky="e", padx=(0, 2))
        ttk.Entry(axis_frame, textvariable=xtitle_var, width=30).grid(row=1, column=1, columnspan=3, sticky="ew", pady=(2, 6))
        
        # Y range
        ttk.Label(axis_frame, text="Y:").grid(row=2, column=0, sticky="e", padx=(0, 2))
        ttk.Entry(axis_frame, textvariable=ymin_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(axis_frame, text="to").grid(row=2, column=2, sticky="w", padx=2)
        ttk.Entry(axis_frame, textvariable=ymax_var, width=8).grid(row=2, column=3, sticky="w")
        
        # Y Title
        ttk.Label(axis_frame, text="Y Title:").grid(row=3, column=0, sticky="e", padx=(0, 2))
        ttk.Entry(axis_frame, textvariable=ytitle_var, width=30).grid(row=3, column=1, columnspan=3, sticky="ew")

        # Define helper functions that will be used by buttons
        def reset_to_defaults() -> None:
            """Reset all controls to default values."""
            logx_var.set(False)
            logy_var.set(True)
            show_markers_var.set(True)
            xmin_var.set(default_xmin)
            xmax_var.set(default_xmax)
            ymin_var.set(default_ymin)
            ymax_var.set(default_ymax)
            title_var.set(current_title or "")
            xtitle_var.set(current_xtitle or "")
            ytitle_var.set(current_ytitle or "")

        def open_canvas() -> None:
            try:
                # build_options will be defined later
                options = build_options()
                if options is None:
                    return

                obj_path = path
                self._root_object_manager.open_object(root_path, obj_path)
            except Exception as e:
                pass

        def save() -> None:
            # Extract filename from root_path for subdirectory, use histogram name for file stem
            file_basename = os.path.splitext(os.path.basename(root_path))[0]
            hist_name = obj.GetName()
            options = build_options()

            # Build peaks list at tab level and pass it to the dialog for export
            peaks_list = None
            try:
                peaks_list = list(peak_finder.peaks) if peak_finder is not None and getattr(peak_finder, "peaks", None) is not None else None
            except Exception:
                peaks_list = None

            AdvancedSaveDialog(
                app,
                app.ROOT,
                obj,
                default_name=hist_name,
                peak_finder=peaks_list,
                subdirectory=file_basename,
                render_options=options,
                fit_states=None,
            )

        # Titles frame
        titles_frame = ttk.Frame(controls)
        titles_frame.grid(row=0, column=1, sticky="new", padx=(0, 10), rowspan=2)
        
        ttk.Label(titles_frame, text="Title:").grid(row=0, column=0, sticky="e", padx=(0, 2))
        ttk.Entry(titles_frame, textvariable=title_var).grid(row=0, column=1, sticky="ew")
        
        # Buttons between title and checkboxes
        button_row_frame = ttk.Frame(titles_frame)
        button_row_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 4))
        ttk.Button(button_row_frame, text="Save", command=lambda: save()).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(button_row_frame, text="Reset", command=reset_to_defaults).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(button_row_frame, text="Open Canvas", command=open_canvas).pack(side=tk.LEFT)
        
        # Checkboxes below buttons
        checkbox_frame = ttk.Frame(titles_frame)
        checkbox_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 0))
        ttk.Checkbutton(checkbox_frame, text="Log X", variable=logx_var).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Checkbutton(checkbox_frame, text="Log Y", variable=logy_var).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Checkbutton(checkbox_frame, text="Show Markers", variable=show_markers_var).pack(side=tk.LEFT)
        
        titles_frame.columnconfigure(1, weight=1)
        
        # Peak finder controls in third column (row 1)
        peak_controls_frame = ttk.Frame(controls)
        peak_controls_frame.grid(row=1, column=2, sticky="nw", rowspan=1)
        
        # Configure main columns
        controls.columnconfigure(1, weight=1)
        # Configure main columns
        controls.columnconfigure(1, weight=1)

        # Small separator and toolbar bar between controls and histogram
        sep = ttk.Separator(main_frame, orient="horizontal")
        sep.pack(fill=tk.X, padx=4, pady=(4, 2))

        middle_bar = ttk.Frame(main_frame, height=28)
        middle_bar.pack(fill=tk.X, padx=4, pady=(0, 2))
        # Toolbar placeholder (left side) - tabs can add buttons here later
        toolbar = ttk.Frame(middle_bar)
        toolbar.pack(side=tk.LEFT)

        # Histogram preview takes full width
        label_frame = ttk.Frame(main_frame)
        label_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 4))
        label = ttk.Label(label_frame)
        label.pack(fill=tk.BOTH, expand=True)

        peak_finder_ui_frame = None
        if peak_finder is not None:
            def trigger_render():
                schedule_render()

            # Create peaks display panel at top (row 0)
            peak_frame = ttk.Frame(controls)
            peak_frame.grid(row=0, column=2, rowspan=1, sticky="nsew", padx=0, pady=0)

            ttk.Label(peak_frame, text="Peaks", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=0, pady=(0,4))

            # Use a Treeview so peaks are selectable/editable and add a vertical scrollbar
            tree_frame = ttk.Frame(peak_frame)
            tree_frame.pack(fill=tk.BOTH, expand=True)

            peaks_tree = ttk.Treeview(tree_frame, columns=("energy", "counts", "source"), show="headings", selectmode="extended", height=6)
            peaks_tree.heading("energy", text="Energy (keV)")
            peaks_tree.heading("counts", text="Counts")
            peaks_tree.heading("source", text="Source")
            peaks_tree.column("energy", width=80, anchor="center")
            peaks_tree.column("counts", width=60, anchor="center")
            peaks_tree.column("source", width=80, anchor="center")

            vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=peaks_tree.yview)
            peaks_tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side=tk.RIGHT, fill=tk.Y)
            peaks_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

            # Bind UI events here (histogram tab owns UI behavior)
            def _on_tree_double(event):
                sel = peaks_tree.selection()
                if not sel:
                    return
                iid = sel[0]
                try:
                    # Ask user for new energy value
                    current = peak_finder.get_peak_energy_by_iid(iid)
                    new_energy = simpledialog.askfloat("Edit peak energy", "Energy (keV):", initialvalue=current, parent=app)
                    if new_energy is None:
                        return
                    if peak_finder.set_peak_energy_by_iid(iid, float(new_energy)):
                        schedule_render()
                except Exception as exc:
                    try:
                        messagebox.showerror("Edit peak", f"Failed to edit peak:\n{exc}", parent=app)
                    except Exception:
                        messagebox.showerror("Edit peak", f"Failed to edit peak:\n{exc}")

            peaks_tree.bind("<Double-1>", _on_tree_double)
            peaks_tree.bind("<Delete>", lambda e: (peak_finder.remove_selected_peak(), schedule_render()))

            # Context menu created/handled in the UI layer
            tree_menu = tk.Menu(peaks_tree, tearoff=0)
            tree_menu.add_command(label="Edit peak", command=lambda: _on_tree_double(None))
            tree_menu.add_command(label="Remove peak", command=lambda: (peak_finder.remove_selected_peak(), schedule_render()))

            def _show_tree_menu(event):
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

            peaks_tree.bind("<Button-3>", _show_tree_menu)
            peaks_tree.bind("<Button-2>", _show_tree_menu)
            peaks_tree.bind("<Control-Button-1>", _show_tree_menu)

            # Wire up peak finder to use the Treeview (selectable).
            # The manual peak variable is created and bound below.
            peak_finder.setup(app, peaks_tree, None)
            peak_finder._render_callback = trigger_render

            peak_finder_ui_frame = peak_frame
            
            # Add peak finder controls below peaks display (row 1)
            ttk.Label(peak_controls_frame, text="Manual peak (keV):").pack(side=tk.LEFT, padx=(0, 2))
            manual_peak_var = tk.StringVar(value="")
            peak_finder._manual_peak_var = manual_peak_var
            manual_entry = ttk.Entry(peak_controls_frame, textvariable=manual_peak_var, width=10)
            manual_entry.pack(side=tk.LEFT, padx=(0, 2))
            def _on_manual_enter(event):
                try:
                    peak_finder._add_manual_peak()
                    trigger_render()
                except Exception:
                    pass
                # Stop further event propagation so the Notebook/tree don't handle Enter
                return "break"

            manual_entry.bind("<Return>", _on_manual_enter)
            manual_entry.bind("<KP_Enter>", _on_manual_enter)
            
            ttk.Button(peak_controls_frame, text="Add", command=lambda: (peak_finder._add_manual_peak(), trigger_render())).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(peak_controls_frame, text="Find Peaks", command=lambda: (peak_finder._find_peaks(app))).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(peak_controls_frame, text="Clear", command=lambda: (peak_finder._clear_peaks(), trigger_render())).pack(side=tk.LEFT, padx=(0, 2))
            ttk.Button(peak_controls_frame, text="Auto Fit", command=peak_finder._auto_fit_peaks).pack(side=tk.LEFT)

        def parse_float(value: str, field_name: str) -> float | None:
            if value.strip() == "":
                return None
            try:
                return float(value)
            except ValueError:
                messagebox.showerror("Invalid value", f"{field_name} must be a number")
                return None

        def build_options() -> dict | None:
            xmin = parse_float(xmin_var.get(), "Xmin")
            xmax = parse_float(xmax_var.get(), "Xmax")
            ymin = parse_float(ymin_var.get(), "Ymin")
            ymax = parse_float(ymax_var.get(), "Ymax")

            markers = []
            if show_markers_var.get() and peak_finder is not None:
                # Only show markers for manual peaks to differentiate from automatic
                markers = [peak["energy"] for peak in peak_finder.peaks if peak.get("source") == "manual"]
            
            options = {
                "logx": logx_var.get(),
                "logy": logy_var.get(),
                "show_markers": show_markers_var.get(),
                "title": title_var.get().strip(),
                "xtitle": xtitle_var.get().strip(),
                "ytitle": ytitle_var.get().strip(),
                "markers": markers,
            }
            
            # Only add range if both min and max are provided
            # AND if log scale is enabled, don't include range if min is 0 (can't render)
            if xmin is not None and xmax is not None:
                if not (logx_var.get() and xmin <= 0):
                    options["xmin"] = xmin
                    options["xmax"] = xmax
            
            if ymin is not None and ymax is not None:
                if not (logy_var.get() and ymin <= 0):
                    options["ymin"] = ymin
                    options["ymax"] = ymax
            
            return options

        pending_after = {"id": None}

        def schedule_render() -> None:
            if pending_after["id"] is not None:
                app.after_cancel(pending_after["id"])
            pending_after["id"] = app.after(150, render_async)

        def render_async() -> None:
            pending_after["id"] = None
            options = build_options()
            if options is None:
                return
            try:
                self._hist_renderer.render_into_label_async(app.ROOT, obj, label, options, delay_ms=0)
            except Exception as exc:
                print(f"Render error: {exc}")
        # Set up traces after initial values are set to avoid triggering renders during setup
        trace_vars = [logx_var, logy_var, show_markers_var, xmin_var, xmax_var, ymin_var, ymax_var, title_var, xtitle_var, ytitle_var]
        
        def add_traces():
            for var in trace_vars:
                var.trace_add("write", lambda *args: schedule_render())
        
        label.bind("<Configure>", lambda e: schedule_render())

        # Do initial render, then add traces and populate axis values
        def do_initial_render():
            render_async()
            # After initial render, populate the axis range fields with defaults
            xmin_var.set(default_xmin)
            xmax_var.set(default_xmax)
            ymin_var.set(default_ymin)
            ymax_var.set(default_ymax)
            add_traces()
        
        app.after(50, do_initial_render)
        
        # Trigger initial peak finding
        app.after(50, lambda: peak_finder._find_peaks(app))

        # Expose small callbacks on this controller so the manager can
        # request a render or peak-find when showing an already-open tab.
        try:
            self._schedule_render = schedule_render
            self._trigger_find_peaks = lambda: peak_finder._find_peaks(app)
        except Exception:
            self._schedule_render = None
            self._trigger_find_peaks = None
        
        return main_frame

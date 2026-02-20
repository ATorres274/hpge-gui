"""Fitting module: UI orchestration for ROOT histogram fitting.

Delegates all pure computation (parameter estimation, ROOT TF1 fitting,
result extraction and formatting) to ``features.fit_feature.FitFeature``.
The module itself only owns UI construction and state management.

Callbacks injected at construction time::

    on_save(fit_state: dict) -> None
        Called when the user requests to save a fit result.  The owning tab
        should implement saving / exporting from *fit_state*.

    on_preview_render(hist_clone, options: dict, image_label) -> None
        Called after a successful fit to request a preview render of the
        fitted histogram clone.  The owning tab provides the renderer.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .error_dispatcher import get_dispatcher, ErrorLevel
from features.fit_feature import FitFeature


class FittingFeature:
    name = "Fitting"

    def __init__(
        self,
        on_save=None,
        on_preview_render=None,
    ) -> None:
        self.fit_frame: ttk.Frame | None = None
        self.current_hist = None
        self.current_hist_clone = None  # Clone for fitting without affecting original
        # Module does not own preview/export/save managers; UI/tab handles those
        self._app = None
        self._dispatcher = get_dispatcher()
        # Callbacks provided by the owning tab
        self._on_save = on_save
        self._on_preview_render = on_preview_render
        self.detected_peaks: list[dict] = []
        self.peak_tabs: dict[int, dict] = {}
        self.current_peak_index: int | None = None
        self.fit_container: ttk.Frame | None = None
        self.fit_count: int = 0  # Counter for fit naming
        self.fit_states: dict[int, dict] = {}  # Store all fit states by fit ID
        self.fit_frames: dict[int, ttk.Frame] = {}  # Store fit frame widgets by fit ID
        self.current_fit_id: int | None = None
        self.fit_dropdown_var: tk.StringVar | None = None
        self.title_label: ttk.Label | None = None

    def __del__(self) -> None:
        """Clean up resources."""
        try:
            pass
        except Exception:
            pass

    def build_ui(self, app, parent: ttk.Frame) -> None:
        self._app = app
        self.fit_frame = parent
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Title and Add Fit button
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        self.title_label = ttk.Label(header_frame, text="Histogram Fitting", font=("TkDefaultFont", 12, "bold"))
        self.title_label.pack(side=tk.LEFT, anchor="w")

        # Exporting and save UI is handled by the owning tab; feature provides data only.
        ttk.Button(header_frame, text="+ Add Fit", command=lambda: self._add_fit_tab()).pack(side=tk.RIGHT, padx=4)

        # Peak tabs area (created on-demand when peaks are set)
        self.peak_tabs_notebook: ttk.Notebook | None = None

        # Fit container with dropdown and content area
        fit_container_frame = ttk.Frame(main_container)
        fit_container_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        fit_dropdown_frame = ttk.Frame(fit_container_frame)
        fit_dropdown_frame.pack(fill=tk.X, padx=0, pady=(0, 8))

        ttk.Label(fit_dropdown_frame, text="Select Fit:").pack(side=tk.LEFT, padx=(0, 6))
        self.fit_dropdown_var = tk.StringVar(value="")
        self.fit_dropdown = ttk.Combobox(
            fit_dropdown_frame,
            textvariable=self.fit_dropdown_var,
            values=[],
            state="readonly",
            width=40,
        )
        self.fit_dropdown.pack(side=tk.LEFT, padx=(0, 6), expand=True, fill=tk.X)
        self.fit_dropdown.bind("<<ComboboxSelected>>", lambda e: self._on_fit_dropdown_changed())

        # Content area for fit display
        self.fit_container = ttk.Frame(fit_container_frame)
        self.fit_container.pack(fill=tk.BOTH, expand=True)

        # Bind to visibility event to update when tab is shown
        parent.bind("<Visibility>", lambda e: self._on_tab_shown())

    def on_selection(self, app, obj, path: str) -> None:
        self.current_hist = obj
        # Create a clone for fitting to avoid modifying the original
        if obj is not None:
            self.current_hist_clone = FitFeature.clone_histogram(obj)
            if self.current_hist_clone is obj:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to clone histogram for fitting, using original",
                    context="FittingFeature.on_selection",
                )
        else:
            self.current_hist_clone = None
        # Update title with histogram name
        if obj is not None and self.title_label is not None:
            hist_name = obj.GetName() if hasattr(obj, "GetName") else "Histogram"
            self.title_label.configure(text=f"Fitting: {hist_name}")

    def _on_tab_shown(self) -> None:
        """Called when the Fit tab is shown."""
        pass  # No automatic preview needed anymore

    def _create_peak_tab(self, idx: int, peak: dict) -> None:
        """Create a tab for a detected peak with auto-filled energy and width."""
        energy = peak.get("energy", 0)
        counts = peak.get("counts", 0)

        # Estimate width from peak FWHM (approximate as 5% of peak energy)
        estimated_width = max(energy * 0.05, 10)  # At least 10 keV width

        # Create tab frame
        tab_frame = ttk.Frame(self.peak_tabs_notebook)
        self.peak_tabs_notebook.add(tab_frame, text=f"Peak {idx+1} ({energy:.0f} keV)")

        # Store tab info
        self.peak_tabs[idx] = {
            "frame": tab_frame,
            "energy": energy,
            "width": estimated_width,
            "index": idx,
        }

        # Create content
        content = ttk.Frame(tab_frame)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Peak info
        info_frame = ttk.LabelFrame(content, text="Peak Information", padding=4)
        info_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(info_frame, text=f"Energy: {energy:.2f} keV").pack(anchor="w")
        ttk.Label(info_frame, text=f"Counts: {counts:.1f}").pack(anchor="w")
        ttk.Label(info_frame, text=f"Est. Width: {estimated_width:.2f} keV").pack(anchor="w")

        # Fit button
        ttk.Button(
            content,
            text="Fit This Peak",
            command=lambda: self._fit_peak(idx)
        ).pack(pady=8)

    def set_peaks(self, peaks: list[dict] | None) -> None:
        """Update detected peaks shown in the UI.

        This method allows the owning tab to provide a plain list of peaks
        (dictionaries). Modules should not call each other directly; the
        tab code is responsible for calling this with data from a
        PeakFinder or other source.
        """
        peaks = peaks or []
        self.detected_peaks = list(peaks)

        # Create the notebook/container if necessary
        if getattr(self, "peak_tabs_notebook", None) is None:
            # need a parent frame to attach to
            if self.fit_frame is None:
                return
            peak_tabs_frame = ttk.LabelFrame(self.fit_frame, text="Detected Peaks", padding=4)
            peak_tabs_frame.pack(fill=tk.X, padx=8, pady=4)
            self.peak_tabs_notebook = ttk.Notebook(peak_tabs_frame)
            self.peak_tabs_notebook.pack(fill=tk.X, expand=True)
            self.peak_tabs_notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_peak_tab_changed())

        # Clear existing peak tabs
        try:
            # remove all tabs from notebook
            if self.peak_tabs_notebook is not None:
                for tab_id in list(self.peak_tabs_notebook.tabs()):
                    try:
                        self.peak_tabs_notebook.forget(tab_id)
                    except Exception as e:
                        self._dispatcher.emit(
                            ErrorLevel.INFO,
                            "Failed to remove peak notebook tab",
                            context="FittingFeature.set_peaks",
                            exception=e
                        )
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to clear peak tabs",
                context="FittingFeature.set_peaks",
                exception=e
            )

        self.peak_tabs.clear()

        for idx, peak in enumerate(self.detected_peaks):
            self._create_peak_tab(idx, peak)

    def _on_peak_tab_changed(self) -> None:
        """Handle peak tab selection change."""
        try:
            selected_tab = self.peak_tabs_notebook.select()
            if selected_tab:
                tab_idx = self.peak_tabs_notebook.index(selected_tab)
                if tab_idx in self.peak_tabs:
                    self.current_peak_index = tab_idx
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to handle peak tab change",
                context="FittingFeature._on_peak_tab_changed",
                exception=e
            )

    def _fit_peak(self, peak_idx: int) -> None:
        """Fit a specific detected peak by creating a new fit tab."""
        if peak_idx not in self.peak_tabs:
            return

        peak_data = self.peak_tabs[peak_idx]

        # Create a new fit tab with the peak's energy and width pre-filled
        self._add_fit_tab(energy=peak_data["energy"], width=peak_data["width"], peak_idx=peak_idx)

    def _add_fit_tab(self, energy: float | None = None, width: float | None = None, peak_idx: int | None = None, auto_fit: bool = False) -> None:
        """Create a new fit in the dropdown list."""
        self.fit_count += 1
        fit_id = self.fit_count  # Use fit number as unique identifier

        fit_name = f"Fit {self.fit_count}"
        if energy is not None:
            fit_name = f"Fit {self.fit_count} ({energy:.0f} keV)"

        # Create fit UI within this fit and store fit_state globally
        tab_frame = ttk.Frame(self.fit_container)
        fit_state = self._create_fit_ui(tab_frame, energy=energy, width=width, peak_idx=peak_idx, fit_id=fit_id)
        self.fit_states[fit_id] = fit_state  # Store globally for access across fits
        self.fit_frames[fit_id] = tab_frame
        fit_state["fit_frame"] = tab_frame

        # Update dropdown with new fit
        current_values = list(self.fit_dropdown.cget("values"))
        current_values.append(fit_name)
        self.fit_dropdown.config(values=current_values)
        
        # Select the new fit
        self.fit_dropdown.set(fit_name)
        self.current_fit_id = fit_id
        self._on_fit_dropdown_changed()

        # If auto_fit is True, automatically perform the fit
        if auto_fit:
            self._app.after(100, lambda: self._perform_fit_for_tab(self._app, fit_state))

    def _create_fit_ui(self, tab_frame: ttk.Frame, energy: float | None = None, width: float | None = None, peak_idx: int | None = None, fit_id: int | None = None) -> None:
        """Create the fitting UI for a single fit."""
        # Store fit-specific state
        fit_state = {
            "fit_id": fit_id,
            "fit_func_var": tk.StringVar(value="gaus"),
            "fit_options_var": tk.StringVar(value="SQ"),
            "energy_var": tk.StringVar(value=f"{energy:.2f}" if energy is not None else ""),
            "width_var": tk.StringVar(value=str(width) if width is not None else ""),
            "params_frame": None,
            "param_entries": [],
            "param_fixed_vars": [],
            "left_frame": None,
            "right_frame": None,
            "image_label": None,
            "image_ref": None,
            "fit_result": None,  # ROOT fit result object (short-lived)
            "cached_results": None,  # Native Python types (persistent)
            "fit_result_text": None,
            "refit_pending": {"id": None},
            "peak_idx": peak_idx,
            "has_fit": False,
            "fit_epoch": 0,
            "fit_func_obj": None,
        }

        main_container = ttk.Frame(tab_frame)
        main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Controls: Fit Function, Energy, Width, Fit button
        controls = ttk.Frame(main_container)
        controls.pack(fill=tk.X, pady=4)

        ttk.Label(controls, text="Fit Function:").grid(row=0, column=0, sticky="e", padx=(0, 6))
        fit_func_combo = ttk.Combobox(
            controls,
            textvariable=fit_state["fit_func_var"],
            values=["gaus", "landau", "expo", "pol1", "pol2", "pol3"],
            state="readonly",
            width=12,
        )
        fit_func_combo.grid(row=0, column=1, sticky="w", padx=(0, 12))
        fit_func_combo.bind("<<ComboboxSelected>>", lambda e: self._on_fit_func_changed_for_tab(fit_state))

        ttk.Label(controls, text="Energy (keV):").grid(row=0, column=2, sticky="e", padx=(0, 6))
        ttk.Entry(controls, textvariable=fit_state["energy_var"], width=10).grid(row=0, column=3, sticky="w", padx=(0, 12))

        ttk.Label(controls, text="Width (keV):").grid(row=0, column=4, sticky="e", padx=(0, 6))
        ttk.Entry(controls, textvariable=fit_state["width_var"], width=10).grid(row=0, column=5, sticky="w", padx=(0, 12))

        ttk.Label(controls, text="Fit Options:").grid(row=0, column=6, sticky="e", padx=(0, 6))
        ttk.Entry(controls, textvariable=fit_state["fit_options_var"], width=10).grid(row=0, column=7, sticky="w", padx=(0, 12))
        
        ttk.Button(controls, text="Fit", command=lambda: self._perform_fit_for_tab(self._app, fit_state)).grid(
            row=0, column=8, padx=12
        )

        # Parameters frame — initial labels come from FitFeature
        fit_state["params_frame"] = ttk.LabelFrame(main_container, text="Initial Parameters (Gaussian)")
        fit_state["params_frame"].pack(fill=tk.X, pady=4)

        param_names = FitFeature.get_param_labels("gaus")
        for i, name in enumerate(param_names):
            ttk.Label(fit_state["params_frame"], text=f"{name}:").grid(row=0, column=i*3, sticky="e", padx=(4, 2))
            var = tk.StringVar(value="")
            entry = ttk.Entry(fit_state["params_frame"], textvariable=var, width=10)
            entry.grid(row=0, column=i*3+1, sticky="w", padx=(0, 4))
            var.trace_add("write", lambda *args, fs=fit_state: self._schedule_refit_for_tab(fs))

            fixed_var = tk.BooleanVar(value=False)
            checkbox = ttk.Checkbutton(fit_state["params_frame"], text="Fix", variable=fixed_var)
            checkbox.grid(row=0, column=i*3+2, sticky="w", padx=(0, 12))

            fit_state["param_entries"].append(var)
            fit_state["param_fixed_vars"].append(fixed_var)

        # Layout: preview on left, results on right
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=8)

        fit_state["left_frame"] = ttk.Frame(content_frame)
        fit_state["left_frame"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        fit_state["image_label"] = ttk.Label(fit_state["left_frame"], text="No fit yet", foreground="gray")
        fit_state["image_label"].pack(fill=tk.BOTH, expand=True)

        fit_state["right_frame"] = ttk.Frame(content_frame)
        fit_state["right_frame"].pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(8, 0))
        fit_state["right_frame"].pack_propagate(False)
        fit_state["right_frame"].config(width=400)

        ttk.Label(fit_state["right_frame"], text="Results", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", padx=4, pady=(0, 4))

        fit_state["fit_result_text"] = tk.Text(fit_state["right_frame"], height=12, wrap=tk.WORD, width=40)
        fit_state["fit_result_text"].pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        fit_state["fit_result_text"].config(state=tk.DISABLED)

        button_frame = ttk.Frame(fit_state["right_frame"])
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=4)

        # Save button — delegates to on_save callback provided by the owning tab.
        if self._on_save is not None:
            ttk.Button(
                button_frame,
                text="Save Fit",
                command=lambda fs=fit_state: self._invoke_save(fs),
            ).pack(side=tk.LEFT, padx=(0, 4))

        # Store fit state in frame for future reference (bidirectional)
        tab_frame.fit_state = fit_state

        return fit_state

    def _on_fit_dropdown_changed(self) -> None:
        """Handle fit dropdown selection change."""
        fit_name = self.fit_dropdown_var.get()
        if not fit_name:
            return
        
        # Find fit_id from the fit name
        for fit_id, fit_state in self.fit_states.items():
            fit_display_name = f"Fit {fit_id}"
            if "energy_var" in fit_state:
                try:
                    energy = float(fit_state["energy_var"].get().strip())
                    fit_display_name = f"Fit {fit_id} ({energy:.0f} keV)"
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to parse energy from fit state",
                        context="FittingFeature._on_fit_dropdown_changed",
                        exception=e
                    )
            if fit_display_name == fit_name:
                self.current_fit_id = fit_id
                self._show_fit_frame(fit_id)
                return

    def _show_fit_frame(self, fit_id: int) -> None:
        """Show the fit frame for the given fit_id."""
        # Hide all fit frames
        for frame in self.fit_frames.values():
            frame.pack_forget()
        
        # Show the selected fit frame
        if fit_id in self.fit_frames:
            self.fit_frames[fit_id].pack(fill=tk.BOTH, expand=True)

    def _on_fit_func_changed_for_tab(self, fit_state: dict) -> None:
        """Update parameter labels when fit function changes for a specific tab."""
        fit_func = fit_state["fit_func_var"].get()
        expected_params = FitFeature.get_param_labels(fit_func)
        current_param_count = len(fit_state["param_entries"])

        if len(expected_params) != current_param_count:
            for widget in fit_state["params_frame"].winfo_children():
                widget.destroy()

            fit_state["param_entries"] = []
            fit_state["param_fixed_vars"] = []

            for i, name in enumerate(expected_params):
                ttk.Label(fit_state["params_frame"], text=f"{name}:").grid(row=0, column=i*3, sticky="e", padx=(4, 2))
                var = tk.StringVar(value="")
                entry = ttk.Entry(fit_state["params_frame"], textvariable=var, width=10)
                entry.grid(row=0, column=i*3+1, sticky="w", padx=(0, 4))
                var.trace_add("write", lambda *args, fs=fit_state: self._schedule_refit_for_tab(fs))

                fixed_var = tk.BooleanVar(value=False)
                checkbox = ttk.Checkbutton(fit_state["params_frame"], text="Fix", variable=fixed_var)
                checkbox.grid(row=0, column=i*3+2, sticky="w", padx=(0, 12))

                fit_state["param_entries"].append(var)
                fit_state["param_fixed_vars"].append(fixed_var)

            fit_state["params_frame"].configure(text=f"Initial Parameters ({fit_func})")

    def _schedule_refit_for_tab(self, fit_state: dict) -> None:
        """Schedule a refit for a specific tab with debounce."""
        if fit_state["refit_pending"]["id"] is not None:
            self._app.after_cancel(fit_state["refit_pending"]["id"])
        fit_state["refit_pending"]["id"] = self._app.after(500, lambda: self._perform_fit_for_tab(self._app, fit_state))

    def _on_fit_tab_changed(self) -> None:
        """Auto-fit when switching to a new fit that has valid range and no fit yet."""
        if self.current_fit_id is None:
            return
        fit_state = self.fit_states.get(self.current_fit_id)
        if not fit_state or fit_state.get("has_fit"):
            return
        if self._has_valid_fit_range(fit_state):
            self._perform_fit_for_tab(self._app, fit_state)

    def _has_valid_fit_range(self, fit_state: dict) -> bool:
        """Check if energy and width are valid numeric values."""
        try:
            energy = float(fit_state["energy_var"].get().strip())
            width = float(fit_state["width_var"].get().strip())
            return energy > 0 and width > 0
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to validate fit range values",
                context="FittingFeature._has_valid_fit_range",
                exception=e
            )
            return False

    def _default_fit_params(self, fit_func: str, fit_state: dict, xmin: float, xmax: float) -> list[float]:
        """Delegate to FitFeature.default_fit_params using current fit-state vars."""
        try:
            energy_str = fit_state["energy_var"].get().strip()
            energy = float(energy_str) if energy_str else None
        except Exception:
            energy = None

        try:
            width_str = fit_state["width_var"].get().strip()
            width = float(width_str) if width_str else None
        except Exception:
            width = None

        return FitFeature.default_fit_params(
            fit_func, self.current_hist_clone, energy, width, xmin, xmax
        )

    def _perform_fit_for_tab(self, app, fit_state: dict) -> None:
        """Perform fit for a specific tab, delegating ROOT computation to FitFeature."""
        if self.current_hist is None:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "No histogram selected for fitting",
                context="FittingFeature._perform_fit_for_tab",
            )
            return

        # Ensure clone exists
        if self.current_hist_clone is None:
            self.current_hist_clone = FitFeature.clone_histogram(self.current_hist)

        if fit_state is None:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Invalid fit state",
                context="FittingFeature._perform_fit_for_tab",
            )
            return

        try:
            root = self._get_root_module(app)
            if root is None:
                return

            # Reset fit state for a fresh run
            fit_state["cached_results"] = None
            fit_state["has_fit"] = False
            fit_state["fit_result"] = None
            fit_state["fit_func_obj"] = None
            fit_state["fit_epoch"] += 1

            fit_func = fit_state["fit_func_var"].get()
            fit_range = self._get_fit_range_for_tab(fit_state)

            xaxis = (
                self.current_hist_clone.GetXaxis()
                if hasattr(self.current_hist_clone, "GetXaxis")
                else None
            )
            default_xmin = float(xaxis.GetXmin()) if xaxis else 0
            default_xmax = float(xaxis.GetXmax()) if xaxis else 10000
            xmin = fit_range[0] if fit_range[0] is not None else default_xmin
            xmax = fit_range[1] if fit_range[1] is not None else default_xmax

            params = []
            for v in fit_state["param_entries"]:
                raw = v.get().strip()
                if not raw:
                    continue
                try:
                    params.append(float(raw))
                except ValueError as exc:
                    self._dispatcher.emit(
                        ErrorLevel.WARNING,
                        f"Non-numeric initial parameter value ignored: {raw!r}",
                        context="FittingFeature._perform_fit_for_tab",
                        exception=exc,
                    )
            fixed_params = [v.get() for v in fit_state["param_fixed_vars"]]

            if not params:
                params = self._default_fit_params(fit_func, fit_state, xmin, xmax)

            fit_option = fit_state["fit_options_var"].get().strip() or "SQ"

            cached, fit_obj = FitFeature.perform_fit(
                root,
                self.current_hist_clone,
                fit_func,
                fit_state["fit_id"],
                fit_state["fit_epoch"],
                xmin,
                xmax,
                params,
                fixed_params,
                fit_option,
                prev_func_obj=fit_state.get("fit_func_obj"),
            )

            fit_state["cached_results"] = cached
            fit_state["fit_func_obj"] = fit_obj
            fit_state["has_fit"] = "error" not in cached

            self._render_fit_preview_for_tab(fit_state)
            self._display_fit_results_for_tab(fit_state)

        except Exception as e:
            import traceback
            error_msg = f"Fit failed: {e}\n{traceback.format_exc()}"
            self._show_results_for_tab(fit_state, error_msg)

    def _get_fit_range_for_tab(self, fit_state: dict) -> tuple[float | None, float | None]:
        """Extract (xmin, xmax) from fit-state energy/width vars via FitFeature."""
        try:
            energy_str = fit_state["energy_var"].get().strip()
            width_str = fit_state["width_var"].get().strip()
            energy = float(energy_str) if energy_str else None
            width = float(width_str) if width_str else None
            return FitFeature.get_fit_range(energy, width)
        except ValueError as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Invalid fit range values provided",
                context="FittingFeature._get_fit_range_for_tab",
                exception=e,
            )
            return (None, None)

    def _render_fit_preview_for_tab(self, fit_state: dict) -> None:
        """Invoke the on_preview_render callback or show a placeholder.

        The owning tab provides a renderer via the ``on_preview_render``
        callback injected at construction time.  When no callback is
        registered the left pane shows a text placeholder instead.
        """
        if self._on_preview_render is not None and callable(self._on_preview_render):
            try:
                self._on_preview_render(
                    self.current_hist_clone,
                    {},
                    fit_state.get("image_label"),
                )
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Preview render callback failed",
                    context="FittingFeature._render_fit_preview_for_tab",
                    exception=e,
                )
        else:
            # Fallback: show a text placeholder when no renderer is connected.
            try:
                for widget in fit_state["left_frame"].winfo_children():
                    widget.destroy()
                fit_state["image_label"] = ttk.Label(
                    fit_state["left_frame"],
                    text="Fit preview available when tab is connected",
                    foreground="gray",
                )
                fit_state["image_label"].pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to update preview placeholder",
                    context="FittingFeature._render_fit_preview_for_tab",
                    exception=e,
                )

    def _display_fit_results_for_tab(self, fit_state: dict) -> None:
        """Format and display fit results using FitFeature.format_fit_results."""
        if fit_state.get("cached_results") is None:
            return
        text = FitFeature.format_fit_results(
            fit_state["fit_func_var"].get(),
            fit_state["fit_options_var"].get(),
            fit_state["cached_results"],
        )
        self._show_results_for_tab(fit_state, text)

    def _invoke_save(self, fit_state: dict) -> None:
        """Invoke the on_save callback with the current fit state."""
        if self._on_save is not None and callable(self._on_save):
            try:
                self._on_save(fit_state)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.WARNING,
                    "Save callback raised an exception",
                    context="FittingFeature._invoke_save",
                    exception=e,
                )

    def _show_results_for_tab(self, fit_state: dict, text: str) -> None:
        """Show results in a specific tab."""
        if not fit_state["fit_result_text"]:
            return
        fit_state["fit_result_text"].config(state=tk.NORMAL)
        fit_state["fit_result_text"].delete("1.0", tk.END)
        fit_state["fit_result_text"].insert(tk.END, text)
        fit_state["fit_result_text"].config(state=tk.DISABLED)

    def _get_root_module(self, app):
        """Get ROOT module from app or import it directly."""
        if app:
            root = getattr(app, "ROOT", None)
            if root is not None:
                return root
        try:
            import ROOT
            return ROOT
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to import ROOT module",
                context="FittingFeature._get_root_module",
                exception=e
            )
            return None
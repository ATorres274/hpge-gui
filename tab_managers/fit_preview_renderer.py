"""Fit preview renderer — fitting panel UI for the histogram tab.

Analogous to ``HistogramPreviewRenderer``, this class owns *all* fitting UI
construction and event wiring.  It lives in ``tab_managers/`` so it may freely
import ``tkinter``.  All computation and state management are delegated to
``FitModule`` in ``modules/``.

Usage::

    # In the owning tab / app-shell:
    fit_module = FitModule(
        on_save=lambda state: export_fit(state),
    )
    renderer = FitPreviewRenderer(
        fit_module,
        on_preview_render=lambda hist, opts, lbl: render(hist, opts, lbl),
    )
    renderer.build_ui(app, parent_frame)

    # When the user selects a histogram:
    renderer.on_histogram_selected(hist_obj, name="My Histogram")

    # When peaks are found:
    renderer.set_peaks(list_of_peak_dicts)
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from modules.error_dispatcher import get_dispatcher, ErrorLevel
from modules.fit_module import FitModule
from features.fit_feature import FitFeature


class FitPreviewRenderer:
    """Builds and manages the fitting panel UI for a single histogram.

    Architecture note: this class lives in ``tab_managers/`` so it is allowed
    to import ``tkinter``.  All fit computation is delegated to ``FitModule``.
    """

    def __init__(
        self,
        module: FitModule,
        on_preview_render=None,
    ) -> None:
        """
        Args:
            module: The ``FitModule`` instance that owns domain state.
            on_preview_render: ``Callable(hist_clone, options: dict, image_label)``
                called after a successful fit so the owning tab can render
                the fitted histogram clone into the preview ``Label``.
        """
        self._module = module
        self._on_preview_render = on_preview_render
        self._dispatcher = get_dispatcher()
        self._app = None

        # Per-fit UI dictionaries (keyed by fit_id)
        self._fit_frames: dict[int, ttk.Frame] = {}
        self._fit_ui_states: dict[int, dict] = {}

        # Dropdown state
        self._fit_dropdown_var: tk.StringVar | None = None
        self._fit_dropdown: ttk.Combobox | None = None
        self._fit_container: ttk.Frame | None = None

        # Header label
        self._title_label: ttk.Label | None = None

        # Wire the fit-completed callback so results are shown automatically.
        self._module.set_fit_completed_callback(self._on_fit_completed)

    # ------------------------------------------------------------------
    # Top-level UI builder
    # ------------------------------------------------------------------

    def build_ui(self, app, parent: ttk.Frame) -> None:
        """Build the complete fitting panel inside *parent*."""
        self._app = app
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        # Header: title + "Add Fit" button
        header = ttk.Frame(main)
        header.pack(fill=tk.X, padx=8, pady=(8, 4))
        self._title_label = ttk.Label(
            header, text="Histogram Fitting", font=("TkDefaultFont", 12, "bold")
        )
        self._title_label.pack(side=tk.LEFT, anchor="w")
        ttk.Button(header, text="+ Add Fit", command=self._add_fit).pack(
            side=tk.RIGHT, padx=4
        )

        # Fit selector dropdown
        dropdown_frame = ttk.Frame(main)
        dropdown_frame.pack(fill=tk.X, padx=8, pady=(4, 0))
        ttk.Label(dropdown_frame, text="Select Fit:").pack(side=tk.LEFT, padx=(0, 6))
        self._fit_dropdown_var = tk.StringVar(value="")
        self._fit_dropdown = ttk.Combobox(
            dropdown_frame,
            textvariable=self._fit_dropdown_var,
            values=[],
            state="readonly",
            width=40,
        )
        self._fit_dropdown.pack(side=tk.LEFT, padx=(0, 6), expand=True, fill=tk.X)
        self._fit_dropdown.bind(
            "<<ComboboxSelected>>", lambda e: self._on_dropdown_changed()
        )

        # Content area where individual fit cards are packed
        self._fit_container = ttk.Frame(main)
        self._fit_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # ------------------------------------------------------------------
    # Public: histogram selection forwarded from the histogram tab
    # ------------------------------------------------------------------

    def on_histogram_selected(self, hist, name: str = "Histogram") -> None:
        """Notify the renderer that the active histogram has changed."""
        self._module.set_histogram(hist)
        if self._title_label is not None:
            self._title_label.configure(text=f"Fitting: {name}")

    # ------------------------------------------------------------------
    # Public: peaks forwarded from the histogram tab
    # ------------------------------------------------------------------

    def set_peaks(self, peaks: list[dict] | None) -> None:
        """Receive detected peaks from the histogram tab.

        Stores them in the module so that "Fit This Peak" buttons can
        pre-populate energy and width for a new fit.
        """
        self._module.set_peaks(peaks)

    # ------------------------------------------------------------------
    # Fit management
    # ------------------------------------------------------------------

    def _add_fit(
        self,
        energy: float | None = None,
        width: float | None = None,
        peak_idx: int | None = None,
        auto_fit: bool = False,
    ) -> None:
        """Create a new fit entry, build its UI card, and select it."""
        fit_id = self._module.add_fit(energy=energy, width=width, peak_idx=peak_idx)
        fit_name = self._module.get_fit_display_name(fit_id)

        tab_frame = ttk.Frame(self._fit_container)
        ui_state = self._build_fit_card(
            tab_frame, fit_id, energy=energy, width=width, peak_idx=peak_idx
        )
        self._fit_frames[fit_id] = tab_frame
        self._fit_ui_states[fit_id] = ui_state

        # Update dropdown
        current_vals = list(self._fit_dropdown.cget("values"))
        current_vals.append(fit_name)
        self._fit_dropdown.config(values=current_vals)
        self._fit_dropdown.set(fit_name)
        self._show_fit_frame(fit_id)

        if auto_fit and self._app is not None:
            self._app.after(100, lambda fid=fit_id: self._trigger_fit(fid))

    def _build_fit_card(
        self,
        tab_frame: ttk.Frame,
        fit_id: int,
        energy: float | None = None,
        width: float | None = None,
        peak_idx: int | None = None,
    ) -> dict:
        """Build the UI card for a single fit and return its *ui_state* dict."""
        ui_state: dict = {
            "fit_func_var": tk.StringVar(value="gaus"),
            "fit_options_var": tk.StringVar(value="SQ"),
            "energy_var": tk.StringVar(
                value=f"{energy:.2f}" if energy is not None else ""
            ),
            "width_var": tk.StringVar(value=str(width) if width is not None else ""),
            "param_entries": [],
            "param_fixed_vars": [],
            "params_frame": None,
            "left_frame": None,
            "right_frame": None,
            "image_label": None,
            "image_ref": None,
            "fit_result_text": None,
            "refit_pending": {"id": None},
        }

        main = ttk.Frame(tab_frame)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # --- Controls row ---
        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, pady=4)

        ttk.Label(controls, text="Fit Function:").grid(
            row=0, column=0, sticky="e", padx=(0, 6)
        )
        fit_func_combo = ttk.Combobox(
            controls,
            textvariable=ui_state["fit_func_var"],
            values=["gaus", "landau", "expo", "pol1", "pol2", "pol3"],
            state="readonly",
            width=12,
        )
        fit_func_combo.grid(row=0, column=1, sticky="w", padx=(0, 12))
        fit_func_combo.bind(
            "<<ComboboxSelected>>",
            lambda e, us=ui_state: self._on_fit_func_changed(us),
        )

        ttk.Label(controls, text="Energy (keV):").grid(
            row=0, column=2, sticky="e", padx=(0, 6)
        )
        ttk.Entry(controls, textvariable=ui_state["energy_var"], width=10).grid(
            row=0, column=3, sticky="w", padx=(0, 12)
        )

        ttk.Label(controls, text="Width (keV):").grid(
            row=0, column=4, sticky="e", padx=(0, 6)
        )
        ttk.Entry(controls, textvariable=ui_state["width_var"], width=10).grid(
            row=0, column=5, sticky="w", padx=(0, 12)
        )

        ttk.Label(controls, text="Fit Options:").grid(
            row=0, column=6, sticky="e", padx=(0, 6)
        )
        ttk.Entry(controls, textvariable=ui_state["fit_options_var"], width=10).grid(
            row=0, column=7, sticky="w", padx=(0, 12)
        )

        ttk.Button(
            controls,
            text="Fit",
            command=lambda fid=fit_id: self._trigger_fit(fid),
        ).grid(row=0, column=8, padx=12)

        # --- Parameters frame ---
        params_frame = ttk.LabelFrame(main, text="Initial Parameters (Gaussian)")
        params_frame.pack(fill=tk.X, pady=4)
        ui_state["params_frame"] = params_frame
        self._rebuild_param_widgets(ui_state, FitFeature.get_param_labels("gaus"))

        # --- Content: preview left + results right ---
        content = ttk.Frame(main)
        content.pack(fill=tk.BOTH, expand=True, pady=8)

        left = ttk.Frame(content)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        ui_state["left_frame"] = left
        img_label = ttk.Label(left, text="No fit yet", foreground="gray")
        img_label.pack(fill=tk.BOTH, expand=True)
        ui_state["image_label"] = img_label

        right = ttk.Frame(content)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(8, 0))
        right.pack_propagate(False)
        right.config(width=400)
        ui_state["right_frame"] = right

        ttk.Label(
            right, text="Results", font=("TkDefaultFont", 10, "bold")
        ).pack(anchor="w", padx=4, pady=(0, 4))

        result_text = tk.Text(right, height=12, wrap=tk.WORD, width=40)
        result_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        result_text.config(state=tk.DISABLED)
        ui_state["fit_result_text"] = result_text

        btn_frame = ttk.Frame(right)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=4)
        if self._module.has_save_callback():
            ttk.Button(
                btn_frame,
                text="Save Fit",
                command=lambda fid=fit_id: self._module.invoke_save(fid),
            ).pack(side=tk.LEFT, padx=(0, 4))

        tab_frame.ui_state = ui_state
        return ui_state

    def _rebuild_param_widgets(
        self, ui_state: dict, param_names: list[str]
    ) -> None:
        """Destroy and recreate parameter entry widgets in the params frame."""
        frame = ui_state["params_frame"]
        for widget in frame.winfo_children():
            widget.destroy()
        ui_state["param_entries"] = []
        ui_state["param_fixed_vars"] = []
        for i, name in enumerate(param_names):
            ttk.Label(frame, text=f"{name}:").grid(
                row=0, column=i * 3, sticky="e", padx=(4, 2)
            )
            var = tk.StringVar(value="")
            ttk.Entry(frame, textvariable=var, width=10).grid(
                row=0, column=i * 3 + 1, sticky="w", padx=(0, 4)
            )
            var.trace_add("write", lambda *_, us=ui_state: self._schedule_refit(us))
            fixed_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text="Fix", variable=fixed_var).grid(
                row=0, column=i * 3 + 2, sticky="w", padx=(0, 12)
            )
            ui_state["param_entries"].append(var)
            ui_state["param_fixed_vars"].append(fixed_var)

    # ------------------------------------------------------------------
    # UI event handlers
    # ------------------------------------------------------------------

    def _on_dropdown_changed(self) -> None:
        """Switch to the fit selected in the combobox."""
        selected_name = self._fit_dropdown_var.get()
        for fit_id, display_name in self._module.list_fits():
            if display_name == selected_name:
                self._show_fit_frame(fit_id)
                return

    def _show_fit_frame(self, fit_id: int) -> None:
        """Hide all fit cards then show the one for *fit_id*."""
        for frame in self._fit_frames.values():
            frame.pack_forget()
        if fit_id in self._fit_frames:
            self._fit_frames[fit_id].pack(fill=tk.BOTH, expand=True)

    def _on_fit_func_changed(self, ui_state: dict) -> None:
        """Rebuild parameter widgets when the user picks a different function."""
        fit_func = ui_state["fit_func_var"].get()
        new_labels = FitFeature.get_param_labels(fit_func)
        if len(new_labels) != len(ui_state["param_entries"]):
            self._rebuild_param_widgets(ui_state, new_labels)
        ui_state["params_frame"].configure(text=f"Initial Parameters ({fit_func})")

    def _schedule_refit(self, ui_state: dict) -> None:
        """Debounced refit: cancel any pending call and reschedule."""
        if self._app is None:
            return
        if ui_state["refit_pending"]["id"] is not None:
            try:
                self._app.after_cancel(ui_state["refit_pending"]["id"])
            except Exception:
                pass
        for fid, us in self._fit_ui_states.items():
            if us is ui_state:
                ui_state["refit_pending"]["id"] = self._app.after(
                    500, lambda fid=fid: self._trigger_fit(fid)
                )
                return

    # ------------------------------------------------------------------
    # Fit trigger
    # ------------------------------------------------------------------

    def _trigger_fit(self, fit_id: int) -> None:
        """Read current UI vars, push to module, then call ``perform_fit``."""
        ui_state = self._fit_ui_states.get(fit_id)
        if ui_state is None:
            return

        fit_func = ui_state["fit_func_var"].get()
        fit_options = ui_state["fit_options_var"].get().strip() or "SQ"

        try:
            energy_str = ui_state["energy_var"].get().strip()
            energy = float(energy_str) if energy_str else None
        except ValueError:
            energy = None

        try:
            width_str = ui_state["width_var"].get().strip()
            width = float(width_str) if width_str else None
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
                    f"Non-numeric initial parameter value ignored: {raw!r}",
                    context="FitPreviewRenderer._trigger_fit",
                    exception=exc,
                )

        fixed_params = [v.get() for v in ui_state["param_fixed_vars"]]

        self._module.update_fit_params(
            fit_id,
            fit_func=fit_func,
            energy=energy,
            width=width,
            params=params,
            fixed_params=fixed_params,
            fit_options=fit_options,
        )

        root = self._module.get_root_module(self._app)
        if root is None:
            return

        # perform_fit fires on_fit_completed which calls _on_fit_completed below.
        self._module.perform_fit(fit_id, root)

    # ------------------------------------------------------------------
    # Fit completion callback (wired into module at construction)
    # ------------------------------------------------------------------

    def _on_fit_completed(self, fit_id: int, cached: dict) -> None:
        """Update results text and request preview render after a fit."""
        ui_state = self._fit_ui_states.get(fit_id)
        if ui_state is None:
            return

        state = self._module.get_fit_state(fit_id)
        if state is not None:
            text = FitFeature.format_fit_results(
                state.get("fit_func", "gaus"),
                state.get("fit_options", "SQ"),
                cached,
            )
            self._show_result_text(ui_state, text)

        # Invoke preview render callback provided by the owning tab.
        if self._on_preview_render is not None and callable(self._on_preview_render):
            try:
                self._on_preview_render(
                    self._module.current_hist_clone,
                    {},
                    ui_state.get("image_label"),
                )
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Preview render callback failed",
                    context="FitPreviewRenderer._on_fit_completed",
                    exception=e,
                )
        else:
            # Fallback: text placeholder when no renderer is connected.
            try:
                left = ui_state.get("left_frame")
                if left is not None:
                    for w in left.winfo_children():
                        w.destroy()
                    ui_state["image_label"] = ttk.Label(
                        left,
                        text="Fit preview available when tab is connected",
                        foreground="gray",
                    )
                    ui_state["image_label"].pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to update preview placeholder",
                    context="FitPreviewRenderer._on_fit_completed",
                    exception=e,
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_result_text(self, ui_state: dict, text: str) -> None:
        """Display *text* in the read-only results text widget."""
        widget = ui_state.get("fit_result_text")
        if not widget:
            return
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state=tk.DISABLED)


__all__ = ["FitPreviewRenderer"]

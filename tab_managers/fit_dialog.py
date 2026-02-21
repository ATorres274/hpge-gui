"""Fit dialog — standalone Toplevel window for histogram fitting controls.

All fitting UI that was previously embedded in the histogram controls bar
now lives here as a non-modal dialog.  The ``HistogramPreviewRenderer``
creates one instance per histogram and opens it via the "Fit…" button.

Architecture note
-----------------
Only UI code lives here; domain computation is delegated to ``FitModule``
(modules/fit_module.py) and ``FitFeature`` (features/fit_feature.py).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from modules.error_dispatcher import get_dispatcher, ErrorLevel
from features.fit_feature import FitFeature, FIT_FUNCTIONS


class FitDialog:
    """Non-modal dialog for interactive histogram fitting.

    Opens as a ``tk.Toplevel`` attached to *parent*.  Owns the fit listbox,
    per-fit control cards, and a zoomable fit-preview canvas.

    Args:
        parent: The Tk root or Toplevel that owns this dialog.
        fit_module: ``FitModule`` instance that holds the fit state.
        peak_finder: ``PeakFinderModule`` for "Fit All" integration.
        preview_manager: ``HistogramRenderer`` used to render the fit preview.
        app: Top-level application window (for ``after`` scheduling).
        on_fit_completed: Optional callback ``(fit_id, cached) → None``
            called after each fit so the main histogram can be re-rendered.
    """

    def __init__(
        self,
        parent,
        fit_module,
        peak_finder,
        preview_manager,
        app,
        on_fit_completed=None,
    ) -> None:
        self._fit_module = fit_module
        self._peak_finder = peak_finder
        self._preview_manager = preview_manager
        self._app = app
        self._external_on_fit_completed = on_fit_completed
        self._dispatcher = get_dispatcher()

        # Per-fit UI state (mirrors what was in HistogramPreviewRenderer)
        self._fit_frames: dict[int, ttk.Frame] = {}
        self._fit_ui_states: dict[int, dict] = {}
        self._fit_listbox: tk.Listbox | None = None
        self._fit_listbox_ids: list[int] = []
        self._fit_preview_label: tk.Label | None = None

        # Build the Toplevel
        self._window = tk.Toplevel(parent)
        self._window.title("Fit Panel")
        self._window.resizable(True, True)
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._window.minsize(520, 360)

        self._build_ui()

        # Register our callback with the fit module so preview updates when
        # a fit completes (triggered from renderer._fit_trigger).
        if self._fit_module is not None:
            self._fit_module.set_fit_completed_callback(self._on_fit_completed)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Build the main layout: left controls | right preview."""
        main = ttk.Frame(self._window)
        main.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Horizontal split: controls (left) | preview (right)
        paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Left panel: fit list + controls ---
        left = ttk.Frame(paned)
        paned.add(left, weight=1)
        self._build_controls(left)

        # --- Right panel: fit preview ---
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        self._fit_preview_label = tk.Label(right, text="No fit yet", bg="white", fg="gray")
        self._fit_preview_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

    def _build_controls(self, parent: ttk.Frame) -> None:
        """Build fit list and action buttons in *parent*."""
        ttk.Label(
            parent, text="Fits", font=("TkDefaultFont", 9, "bold")
        ).pack(anchor="w", pady=(0, 2))

        # Listbox + scrollbar
        lb_frame = ttk.Frame(parent)
        lb_frame.pack(fill=tk.X)
        self._fit_listbox = tk.Listbox(
            lb_frame, height=5, selectmode=tk.SINGLE,
            exportselection=False, width=24,
        )
        lb_sb = ttk.Scrollbar(lb_frame, orient="vertical",
                               command=self._fit_listbox.yview)
        self._fit_listbox.configure(yscrollcommand=lb_sb.set)
        lb_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._fit_listbox.pack(fill=tk.BOTH, expand=True)
        self._fit_listbox.bind(
            "<<ListboxSelect>>", lambda e: self._on_fit_listbox_changed()
        )

        # Add / Remove / Fit-All buttons
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="+ Fit",
                   command=self._fit_add).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="Remove",
                   command=self._fit_remove_selected).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_row, text="Fit All Peaks",
                   command=self._fit_add_all_peaks).pack(side=tk.LEFT)

        # Container for the active fit's control card
        self._fit_container = ttk.Frame(parent)
        self._fit_container.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    # ------------------------------------------------------------------
    # Fit management (replaces _fit_* methods from renderer)
    # ------------------------------------------------------------------

    def _fit_add(
        self,
        energy: float | None = None,
        width: float | None = None,
        peak_idx: int | None = None,
    ) -> None:
        """Create a new fit entry and show its compact controls card."""
        if self._fit_module is None:
            return
        fit_id = self._fit_module.add_fit(
            energy=energy, width=width, peak_idx=peak_idx
        )
        fit_name = self._fit_module.get_fit_display_name(fit_id)

        card = ttk.Frame(self._fit_container)
        ui_state = self._fit_build_card(card, fit_id, energy=energy, width=width)
        self._fit_frames[fit_id] = card
        self._fit_ui_states[fit_id] = ui_state

        # Pre-fill seed parameters when energy is known
        if energy is not None:
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
        pf = self._peak_finder
        if pf is None or self._fit_module is None:
            return
        for peak in list(pf.peaks):
            energy = peak.get("energy")
            if energy is None:
                continue
            width = self._fit_module.estimate_peak_width(energy)
            self._fit_add(energy=energy, width=width)

    def fit_add_all_peaks(self) -> None:
        """Public API: open and populate a fit for every detected peak."""
        self._fit_add_all_peaks()

    def _fit_prefill_params(
        self,
        fit_id: int,
        ui_state: dict,
        energy: float,
        width: float | None,
    ) -> None:
        """Pre-fill parameter entries with seed values from FitFeature."""
        if self._fit_module is None:
            return
        fit_func = ui_state["fit_func_var"].get()
        hist_clone = (
            self._fit_module.current_hist_clone
            or self._fit_module.current_hist
        )
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
            "fit_func_var":     tk.StringVar(value="gaus"),
            "fit_options_var":  tk.StringVar(value="SQ"),
            "energy_var":       tk.StringVar(
                value=f"{energy:.2f}" if energy is not None else ""
            ),
            "width_var":        tk.StringVar(
                value=str(width) if width is not None else ""
            ),
            "param_entries":    [],
            "param_fixed_vars": [],
            "params_frame":     None,
            "refit_pending":    {"id": None},
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

        params_frame = ttk.LabelFrame(card, text="Initial Parameters (gaus)")
        params_frame.pack(fill=tk.X, pady=(2, 1))
        ui_state["params_frame"] = params_frame
        self._fit_rebuild_params(ui_state, FitFeature.get_param_labels("gaus"))

        return ui_state

    def _fit_rebuild_params(
        self, ui_state: dict, param_names: list[str]
    ) -> None:
        """Destroy and recreate parameter entry widgets in the params frame."""
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
                row=grid_row, column=col_base,
                sticky="e", padx=(2, 1), pady=(1, 0),
            )
            var = tk.StringVar(value="")
            ttk.Entry(frame, textvariable=var, width=7).grid(
                row=grid_row, column=col_base + 1,
                sticky="w", padx=(0, 1), pady=(1, 0),
            )
            var.trace_add(
                "write",
                lambda *_, us=ui_state: self._fit_schedule_refit(us),
            )
            fixed_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text="Fix", variable=fixed_var).grid(
                row=grid_row, column=col_base + 2,
                sticky="w", padx=(0, 4), pady=(1, 0),
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
        if self._fit_listbox is not None:
            try:
                idx = self._fit_listbox_ids.index(fit_id)
                self._fit_listbox.selection_clear(0, tk.END)
                self._fit_listbox.selection_set(idx)
                self._fit_listbox.see(idx)
            except (ValueError, AttributeError):
                pass
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
        app = self._app
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
                    context="FitDialog._fit_trigger",
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

        root = self._fit_module.get_root_module(self._app)
        if root is None:
            return
        self._fit_module.perform_fit(fit_id, root)

    def _render_fit_preview(self, fit_id: int) -> None:
        """Render (or re-render) the zoomed fit preview for *fit_id*."""
        if self._fit_module is None:
            return
        state = self._fit_module.get_fit_state(fit_id)
        if state is None:
            return

        fit_func = state.get("fit_func", "gaus")
        energy   = state.get("energy")
        width    = state.get("width") or 20.0
        cached   = state.get("cached_results")

        pavetext = None
        if cached and "error" not in cached:
            pavetext = FitFeature.format_fit_results_short(fit_func, cached)

        pm        = self._preview_manager
        fit_label = self._fit_preview_label
        if pm is None or fit_label is None:
            return

        root  = self._fit_module.get_root_module(self._app)
        clone = self._fit_module.current_hist_clone
        if root is None or clone is None:
            return

        try:
            preview_opts: dict = {}
            preview_xmin, preview_xmax = None, None

            if cached and "parameters" in cached:
                mean, sigma = FitFeature.peak_sigma_mean(
                    fit_func, cached["parameters"]
                )
                if mean is not None and sigma is not None and sigma > 0:
                    preview_xmin = mean - 4.0 * sigma
                    preview_xmax = mean + 4.0 * sigma

            if preview_xmin is None:
                preview_xmin = state.get("xmin")
                preview_xmax = state.get("xmax")

            if preview_xmin is None and energy is not None:
                try:
                    preview_xmin = float(energy) - float(width) / 2.0
                    preview_xmax = float(energy) + float(width) / 2.0
                except Exception:
                    pass

            if preview_xmin is not None and preview_xmax is not None:
                preview_opts["xmin"] = preview_xmin
                preview_opts["xmax"] = preview_xmax

            xmin = state.get("xmin")
            xmax = state.get("xmax")
            if xmin is None:
                xmin = preview_xmin
                xmax = preview_xmax

            if pavetext:
                preview_opts["pavetext"] = pavetext

            if cached and "parameters" in cached and xmin is not None:
                try:
                    formula  = FitFeature.get_fit_formula(fit_func)
                    tf1_name = f"_dlg_preview_tf1_{fit_id}"
                    fresh_tf1 = root.TF1(tf1_name, formula, xmin, xmax)
                    try:
                        fresh_tf1.SetNpx(500)
                    except Exception:
                        pass
                    for i, p in enumerate(cached["parameters"]):
                        fresh_tf1.SetParameter(i, float(p))
                    preview_opts["fit_func_obj"] = fresh_tf1
                except Exception:
                    pass

            pm.render_into_label_async(
                root, clone, fit_label, options=preview_opts, delay_ms=80
            )
        except Exception as exc:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Fit preview render failed",
                context="FitDialog._render_fit_preview",
                exception=exc,
            )

    def _on_fit_completed(self, fit_id: int, cached: dict) -> None:
        """Called by FitModule after a fit completes."""
        self._render_fit_preview(fit_id)
        # Forward to the renderer so the main histogram preview updates too
        if self._external_on_fit_completed is not None:
            try:
                self._external_on_fit_completed(fit_id, cached)
            except Exception as exc:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "External on_fit_completed callback failed",
                    context="FitDialog._on_fit_completed",
                    exception=exc,
                )

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        """Hide the window instead of destroying it so state is preserved."""
        try:
            self._window.withdraw()
        except Exception:
            pass

    def show(self) -> None:
        """Raise and focus the dialog, or deiconify if minimised."""
        try:
            self._window.deiconify()
            self._window.lift()
            self._window.focus_set()
        except Exception:
            pass

    def is_alive(self) -> bool:
        """Return True when the underlying Toplevel still exists."""
        try:
            return self._window.winfo_exists()
        except Exception:
            return False

    def has_completed_fits(self) -> bool:
        """Return True when at least one fit has completed without error."""
        if self._fit_module is None:
            return False
        states = self._fit_module.get_all_fit_states()
        return any(s.get("has_fit") for s in states.values())

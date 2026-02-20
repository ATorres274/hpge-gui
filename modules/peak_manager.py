"""Peak manager module: composes automatic and manual peak handlers.

UI-facing adapter exposing peak-finding helpers to the histogram tab.
Provides a `PeakFinderModule` class that integrates automatic and
manual peak helpers for use by the histogram tab.
"""

from __future__ import annotations

from typing import Any


from features.peak_search_feature import PeakSearchAutomatic, PeakSearchManual


class PeakFinderModule:
    """UI adapter used by the histogram tab.

    The public API maintains previous feature signatures where practical
    to minimize integration changes.
    """

    name = "Peak Finder"

    def __init__(self) -> None:
        self.automatic = PeakSearchAutomatic()
        self.manual = PeakSearchManual()
        self.current_hist = None
        self.peaks: list[dict] = []
        self._peaks_tree: Any | None = None
        self._peaks_text: Any | None = None
        self._manual_peak_var: Any | None = None
        self._render_callback = None
        self.fitting_feature = None
        self.parent_app = None
        self.host_notebook = None

        # Search parameters — set by the tab layer either via ``set_search_params``
        # or by direct attribute assignment (e.g. ``pf.search_sigma = 5``).
        self.search_sigma: float = 3.0
        self.search_energy_min: float | None = None
        self.search_energy_max: float | None = None
        self.search_threshold_counts: float = 0.0

    def set_search_params(
        self,
        sigma: float | None = None,
        energy_min: float | None = None,
        energy_max: float | None = None,
        threshold_counts: float | None = None,
        *,
        clear_energy_min: bool = False,
        clear_energy_max: bool = False,
    ) -> None:
        """Update automatic-search parameters.

        Called by the tab layer when the user adjusts the search controls.
        Only non-``None`` arguments are updated.  Pass ``clear_energy_min=True``
        or ``clear_energy_max=True`` to explicitly remove the corresponding bound.
        """
        if sigma is not None:
            self.search_sigma = float(sigma)
        if clear_energy_min:
            self.search_energy_min = None
        elif energy_min is not None:
            self.search_energy_min = float(energy_min)
        if clear_energy_max:
            self.search_energy_max = None
        elif energy_max is not None:
            self.search_energy_max = float(energy_max)
        if threshold_counts is not None:
            self.search_threshold_counts = float(threshold_counts)

    def setup(self, app: Any, peaks_widget: Any, manual_peak_var: Any) -> None:
        """Attach UI widgets (Treeview or fallback Text widget) and manual var.

        The UI remains owned by the caller; this module only stores
        references and populates the view when `self._update_peaks_display` is called.
        """
        self.parent_app = app
        # Accept any widget — Treeview is detected by the presence of
        # ``get_children``; anything else is treated as a text widget.
        if hasattr(peaks_widget, "get_children"):
            self._peaks_tree = peaks_widget
        else:
            self._peaks_text = peaks_widget
        self._manual_peak_var = manual_peak_var

    def on_selection(self, app, obj, path: str) -> None:
        self.current_hist = obj
        self.peaks = []
        self._update_peaks_display()
        self._find_peaks(app)

    def _find_peaks(self, app) -> None:
        if self.current_hist is None:
            return

        found = self.automatic.find_peaks(
            app,
            self.current_hist,
            sigma=self.search_sigma,
            energy_min=self.search_energy_min,
            energy_max=self.search_energy_max,
            threshold_counts=self.search_threshold_counts,
        ) or []

        # Preserve manual peaks added by the user; replace only automatic peaks
        manual_peaks = [p for p in self.peaks if p.get("source") == "manual"]

        # Combine automatic (found) + manual, then sort
        new_peaks: list[dict] = []
        if found:
            new_peaks.extend(found)
        if manual_peaks:
            new_peaks.extend(manual_peaks)

        # If no automatic peaks were found, keep manual peaks as-is
        if not new_peaks:
            # nothing changed
            return

        self.peaks = sorted(new_peaks, key=lambda p: p.get("energy", 0.0))
        self._update_peaks_display()
        if self._render_callback:
            self._render_callback()

    def _add_manual_peak(self) -> None:
        if self._manual_peak_var is None:
            return
        raw = self._manual_peak_var.get().strip()
        if not raw:
            return
        try:
            val = float(raw)
        except Exception:
            return
        peak = self.manual.make_manual_peak(val, self.current_hist)
        self.peaks.append(peak)
        self.peaks.sort(key=lambda p: p["energy"])
        self._manual_peak_var.set("")
        self._update_peaks_display()
        if self._render_callback:
            self._render_callback()

    def _update_peaks_display(self) -> None:
        automatic = [p for p in self.peaks if p.get("source") == "automatic"]
        manual = [p for p in self.peaks if p.get("source") == "manual"]
        if self._peaks_tree is not None:
            # Clear
            for iid in list(self._peaks_tree.get_children()):
                self._peaks_tree.delete(iid)
            for i, peak in enumerate(self.peaks):
                energy = f"{peak['energy']:.1f}"
                counts = f"{peak['counts']:.0f}" if peak.get("counts") is not None else ""
                src = peak.get("source", "")
                self._peaks_tree.insert("", "end", iid=str(i), values=(energy, counts, src))
        else:
            auto_lines = []
            if automatic:
                for i, peak in enumerate(automatic, 1):
                    auto_lines.append(f"{i}. {peak['energy']:.1f} keV")
                    if peak.get("counts") is not None:
                        auto_lines.append(f"   Counts: {peak['counts']:.0f}")
                auto_lines.append("")
            text = "\n".join(auto_lines).strip() if auto_lines else "No peaks found"
            if self._peaks_text is not None:
                try:
                    self._peaks_text.config(state="normal")
                    self._peaks_text.delete("1.0", "end")
                    self._peaks_text.insert("end", text)
                    self._peaks_text.config(state="disabled")
                except Exception:
                    pass
        # Notify UI to re-render preview when peaks change
        try:
            if self._render_callback:
                self._render_callback()
        except Exception:
            pass

    def get_peak_energy_by_iid(self, iid: str) -> float | None:
        try:
            idx = int(iid)
        except Exception:
            return None
        if 0 <= idx < len(self.peaks):
            return float(self.peaks[idx].get("energy", 0.0))
        return None

    def set_peak_energy_by_iid(self, iid: str, energy: float) -> bool:
        try:
            idx = int(iid)
        except Exception:
            return False
        if idx < 0 or idx >= len(self.peaks):
            return False
        peak = self.peaks[idx]
        peak["energy"] = float(energy)
        if self.current_hist is not None:
            try:
                peak["counts"] = self.current_hist.GetBinContent(self.current_hist.FindBin(peak["energy"]))
            except Exception:
                peak["counts"] = None
        self.peaks.sort(key=lambda p: p["energy"])
        self._update_peaks_display()
        if self._render_callback:
            self._render_callback()
        return True

    def remove_selected_peak(self) -> None:
        if self._peaks_tree is None:
            return
        sel = self._peaks_tree.selection()
        if not sel:
            return
        indices = []
        for iid in sel:
            try:
                indices.append(int(iid))
            except Exception:
                continue
        for idx in sorted(indices, reverse=True):
            if 0 <= idx < len(self.peaks):
                del self.peaks[idx]
        self._update_peaks_display()
        if self._render_callback:
            self._render_callback()

    def _clear_peaks(self) -> None:
        """Remove all peaks (automatic and manual) and refresh the display."""
        self.peaks = []
        self._update_peaks_display()

    def _export_peaks(self) -> None:
        # Exporting is handled by the tab-level controller.
        # This method is intentionally a no-op; feature authors should
        # access `peak_finder.peaks` and let the tab/export UI perform saving.
        return

    def _auto_fit_peaks(self) -> None:
        """Create fit tabs for all detected peaks using a fixed width.

        Preserves the previous call signature so UI callers can invoke
        `peak_finder._auto_fit_peaks()` without change.
        """
        if not self.peaks:
            return
        if self.fitting_feature is None:
            return

        # Clear existing fit states and frames on the fitting feature
        try:
            self.fitting_feature.fit_states.clear()
            self.fitting_feature.fit_frames.clear()
        except Exception:
            pass

        # Reset counters and dropdowns if present
        try:
            self.fitting_feature.fit_count = 0
            if getattr(self.fitting_feature, 'fit_dropdown', None):
                self.fitting_feature.fit_dropdown.config(values=[])
            if getattr(self.fitting_feature, 'fit_dropdown_var', None):
                self.fitting_feature.fit_dropdown_var.set("")
            self.fitting_feature.current_fit_id = None
        except Exception:
            pass

        # Start creating fit tabs sequentially
        self._create_fit_tabs_sequentially(0)

        # Switch to Fit tab if we have a host_notebook reference
        try:
            if self.host_notebook is not None:
                for i, tab in enumerate(self.host_notebook.tabs()):
                    if "Fit" in self.host_notebook.tab(i, "text"):
                        self.host_notebook.select(tab)
                        break
        except Exception:
            pass

    def _create_fit_tabs_sequentially(self, index: int) -> None:
        """Create fit tabs one at a time with a small delay to avoid races."""
        if index >= len(self.peaks):
            return

        peak = self.peaks[index]
        energy = peak.get("energy", 0)
        width = 10.0

        try:
            # Delegate to fitting feature to add a fit tab; preserve call signature
            self.fitting_feature._add_fit_tab(energy=energy, width=width, peak_idx=None, auto_fit=True)
        except Exception:
            pass

        # Schedule next tab creation
        try:
            if self.parent_app is not None:
                self.parent_app.after(200, lambda: self._create_fit_tabs_sequentially(index + 1))
        except Exception:
            # Fallback: call directly (best-effort)
            try:
                self._create_fit_tabs_sequentially(index + 1)
            except Exception:
                pass


__all__ = ["PeakFinderModule"]

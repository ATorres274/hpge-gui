"""Fit module: domain logic for ROOT histogram fitting.

No UI code lives in this module.  The owning tab manager
(``tab_managers.histogram_preview_renderer.HistogramPreviewRenderer``) handles
all UI construction and event wiring, calling into this module for computation
and state management.

Callbacks injected at construction time::

    on_save(fit_state: dict) -> None
        Called when the user requests to save a fit result.  The owning
        tab should implement file export from *fit_state*.

    on_fit_completed(fit_id: int, cached_results: dict) -> None
        Called after a fit is performed so the tab / renderer can update
        the preview image and result text widget.
"""

from __future__ import annotations

from .error_dispatcher import get_dispatcher, ErrorLevel
from features.fit_feature import FitFeature


class FitModule:
    """Domain module for ROOT histogram fitting.

    Stores plain-Python fit state (no tkinter objects).  The tab layer
    ``HistogramPreviewRenderer`` owns all widget creation and calls this module
    to perform computation and fire callbacks.
    """

    name = "Fitting"

    def __init__(
        self,
        on_save=None,
        on_fit_completed=None,
    ) -> None:
        self.current_hist = None
        self.current_hist_clone = None
        self.detected_peaks: list[dict] = []
        self._fit_count: int = 0
        self._fit_states: dict[int, dict] = {}
        self._current_fit_id: int | None = None
        self._on_save = on_save
        self._on_fit_completed = on_fit_completed
        self._dispatcher = get_dispatcher()

    # ------------------------------------------------------------------
    # Histogram and peaks
    # ------------------------------------------------------------------

    def set_histogram(self, hist) -> None:
        """Store *hist* and create a clone for non-destructive fitting."""
        self.current_hist = hist
        self.current_hist_clone = (
            FitFeature.clone_histogram(hist) if hist is not None else None
        )
        if hist is not None and self.current_hist_clone is hist:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Could not clone histogram for fitting; using original",
                context="FitModule.set_histogram",
            )

    def set_peaks(self, peaks: list[dict] | None) -> None:
        """Store *peaks* (plain dicts from the histogram tab peak finder)."""
        self.detected_peaks = list(peaks or [])

    @staticmethod
    def estimate_peak_width(energy: float) -> float:
        """Estimate a sensible fit window width: 5 % of *energy*, ≥ 10 keV."""
        return max(energy * 0.05, 10.0)

    # ------------------------------------------------------------------
    # Fit state management
    # ------------------------------------------------------------------

    def add_fit(
        self,
        energy: float | None = None,
        width: float | None = None,
        peak_idx: int | None = None,
    ) -> int:
        """Create a new fit entry and return its unique *fit_id*."""
        self._fit_count += 1
        fit_id = self._fit_count
        self._fit_states[fit_id] = {
            "fit_id": fit_id,
            "fit_func": "gaus",
            "fit_options": "SQ",
            "energy": energy,
            "width": width,
            "params": [],
            "fixed_params": [],
            "peak_idx": peak_idx,
            "has_fit": False,
            "fit_epoch": 0,
            "cached_results": None,
            "fit_func_obj": None,
        }
        self._current_fit_id = fit_id
        return fit_id

    def remove_fit(self, fit_id: int) -> None:
        """Remove a fit entry."""
        self._fit_states.pop(fit_id, None)
        if self._current_fit_id == fit_id:
            remaining = list(self._fit_states.keys())
            self._current_fit_id = remaining[-1] if remaining else None

    def get_fit_state(self, fit_id: int) -> dict | None:
        """Return the fit state dict for *fit_id*, or ``None``."""
        return self._fit_states.get(fit_id)

    def list_fits(self) -> list[tuple[int, str]]:
        """Return ``[(fit_id, display_name), …]`` for all tracked fits."""
        return [(fid, self.get_fit_display_name(fid)) for fid in self._fit_states]

    def get_fit_display_name(self, fit_id: int) -> str:
        """Return a human-readable name for *fit_id*."""
        state = self._fit_states.get(fit_id)
        if state is None:
            return f"Fit {fit_id}"
        energy = state.get("energy")
        if energy is not None:
            try:
                return f"Fit {fit_id} ({float(energy):.0f} keV)"
            except (TypeError, ValueError):
                pass
        return f"Fit {fit_id}"

    def update_fit_params(
        self,
        fit_id: int,
        *,
        fit_func: str,
        energy: float | None,
        width: float | None,
        params: list[float],
        fixed_params: list[bool],
        fit_options: str,
    ) -> None:
        """Push UI-supplied parameter values into the fit state before fitting."""
        state = self._fit_states.get(fit_id)
        if state is None:
            return
        state["fit_func"] = fit_func
        state["energy"] = energy
        state["width"] = width
        state["params"] = list(params)
        state["fixed_params"] = list(fixed_params)
        state["fit_options"] = fit_options

    # ------------------------------------------------------------------
    # Fit execution
    # ------------------------------------------------------------------

    def perform_fit(self, fit_id: int, root) -> dict:
        """Execute the ROOT fit for *fit_id* and return the cached-results dict.

        The module fires the ``on_fit_completed`` callback after the fit so
        the owning renderer can update its preview and result text.
        """
        state = self._fit_states.get(fit_id)
        if state is None:
            return {"error": f"Unknown fit ID: {fit_id}"}
        if self.current_hist is None:
            return {"error": "No histogram selected for fitting"}
        if self.current_hist_clone is None:
            self.current_hist_clone = FitFeature.clone_histogram(self.current_hist)

        fit_func = state.get("fit_func", "gaus")
        fit_options = state.get("fit_options") or "SQ"
        energy = state.get("energy")
        width = state.get("width")
        params = list(state.get("params") or [])
        fixed_params = list(state.get("fixed_params") or [])

        fit_range = FitFeature.get_fit_range(energy, width)
        xaxis = (
            self.current_hist_clone.GetXaxis()
            if hasattr(self.current_hist_clone, "GetXaxis")
            else None
        )
        default_xmin = float(xaxis.GetXmin()) if xaxis and hasattr(xaxis, "GetXmin") else 0.0
        default_xmax = float(xaxis.GetXmax()) if xaxis and hasattr(xaxis, "GetXmax") else 10000.0
        xmin = fit_range[0] if fit_range[0] is not None else default_xmin
        xmax = fit_range[1] if fit_range[1] is not None else default_xmax

        if not params:
            params = FitFeature.default_fit_params(
                fit_func, self.current_hist_clone, energy, width, xmin, xmax
            )

        state["fit_epoch"] += 1
        state["has_fit"] = False
        state["cached_results"] = None

        try:
            cached, fit_obj = FitFeature.perform_fit(
                root,
                self.current_hist_clone,
                fit_func,
                fit_id,
                state["fit_epoch"],
                xmin,
                xmax,
                params,
                fixed_params,
                fit_options,
                prev_func_obj=state.get("fit_func_obj"),
            )
        except Exception as exc:
            cached = {"error": str(exc)}
            fit_obj = None

        state["cached_results"] = cached
        state["fit_func_obj"] = fit_obj
        state["has_fit"] = "error" not in cached

        if self._on_fit_completed is not None:
            try:
                self._on_fit_completed(fit_id, cached)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.WARNING,
                    "on_fit_completed callback raised an exception",
                    context="FitModule.perform_fit",
                    exception=e,
                )

        return cached

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def invoke_save(self, fit_id: int) -> None:
        """Fire the ``on_save`` callback with the state of *fit_id*."""
        state = self._fit_states.get(fit_id)
        if state is None:
            return
        if self._on_save is not None and callable(self._on_save):
            try:
                self._on_save(state)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.WARNING,
                    "on_save callback raised an exception",
                    context="FitModule.invoke_save",
                    exception=e,
                )

    def has_save_callback(self) -> bool:
        """Return ``True`` when an ``on_save`` callback has been configured."""
        return self._on_save is not None and callable(self._on_save)

    def set_fit_completed_callback(self, callback) -> None:
        """Register *callback* as the ``on_fit_completed`` handler.

        Use this when the renderer is constructed after the module and needs
        to wire itself in without touching private attributes.
        """
        self._on_fit_completed = callback

    # ------------------------------------------------------------------
    # ROOT helper
    # ------------------------------------------------------------------

    def get_root_module(self, app):
        """Return the ROOT Python module from *app* or by direct import.

        Tries ``app.ROOT`` first so that a cached/shared ROOT object is reused.
        Falls back to ``import ROOT``.

        Returns:
            The ROOT module, or ``None`` when ROOT is unavailable.  Callers
            must check for ``None`` before calling any ROOT API.
        """
        if app:
            root = getattr(app, "ROOT", None)
            if root is not None:
                return root
        try:
            import ROOT  # type: ignore
            return ROOT
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to import ROOT module",
                context="FitModule.get_root_module",
                exception=e,
            )
            return None


# Backward-compatible alias so any code that imported the old class name
# continues to work without modification.
FittingFeature = FitModule

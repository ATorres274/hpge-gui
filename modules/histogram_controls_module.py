"""Histogram controls module: axis-range defaults, scroll steps, validation,
and render-options assembly for the histogram tab.

All logic that was previously inlined inside ``HistogramPreviewRenderer`` in
``tab_managers/histogram_tab.py`` now lives here so the tab layer only handles
UI wiring.

Architecture note (from AGENTS.md)
-----------------------------------
Modules own domain logic; they must **not** import tkinter or hold UI state.
Callers (tab managers) pass values in and receive computed values back.

Log-scale scroll
----------------
When ``log_mode=True`` is passed to ``clamp_min`` / ``clamp_max``, each scroll
tick multiplies (up) or divides (down) the value by ``_LOG_FACTOR`` (≈ 1.122,
i.e. ``10 ** 0.05``).  This gives ~30 ticks to traverse a 1.5-decade HPGe X
axis — quick without overshooting.  In linear mode the existing additive step
is used unchanged.
"""

from __future__ import annotations

import math
from typing import Any

_LOG_FACTOR: float = 10 ** 0.05  # ≈ 1.122 per scroll tick


class HistogramControlsModule:
    """Stateless helper that performs axis-control calculations.

    All methods are pure functions grouped into a class for namespace clarity.
    The tab layer stores tkinter Vars; this module knows nothing about them.
    """

    # ------------------------------------------------------------------
    # Default initialisation
    # ------------------------------------------------------------------

    @staticmethod
    def compute_defaults(obj: Any) -> dict:
        """Extract axis defaults from a histogram object.

        Returns a dict with keys:
            x_min, x_max, y_min, y_max,
            x_scroll_step, y_scroll_step,
            x_label, y_label, title
        """
        xaxis = obj.GetXaxis() if hasattr(obj, "GetXaxis") else None
        yaxis = obj.GetYaxis() if hasattr(obj, "GetYaxis") else None

        try:
            x_min = float(xaxis.GetXmin()) if xaxis is not None else 0.1
            x_max = float(xaxis.GetXmax()) if xaxis is not None else 100.0
        except Exception:
            x_min, x_max = 0.1, 100.0

        if x_min <= 0:
            x_min = 0.1

        try:
            y_min = float(obj.GetMinimum()) if hasattr(obj, "GetMinimum") else 0.1
            y_max = float(obj.GetMaximum()) if hasattr(obj, "GetMaximum") else 120.0
            y_max *= 1.2
        except Exception:
            y_min, y_max = 0.1, 120.0

        if y_min <= 0:
            y_min = 0.1

        x_scroll_step = max(1.0, round(x_max * 0.01, 1))
        y_scroll_step = max(1.0, round(y_max * 0.01, 1))

        x_label = ""
        y_label = ""
        title = ""
        try:
            if xaxis is not None and hasattr(xaxis, "GetTitle"):
                x_label = str(xaxis.GetTitle())
        except Exception:
            pass
        try:
            if yaxis is not None and hasattr(yaxis, "GetTitle"):
                y_label = str(yaxis.GetTitle())
        except Exception:
            pass
        try:
            if hasattr(obj, "GetTitle"):
                title = str(obj.GetTitle())
        except Exception:
            pass

        return {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "x_scroll_step": x_scroll_step,
            "y_scroll_step": y_scroll_step,
            "x_label": x_label,
            "y_label": y_label,
            "title": title,
        }

    # ------------------------------------------------------------------
    # Scroll helpers
    # ------------------------------------------------------------------

    @staticmethod
    def clamp_min(current: float, step: float, direction_down: bool,
                  min_limit: float, max_val: float,
                  log_mode: bool = False) -> float:
        """Return a new validated min value after a scroll event.

        direction_down=True  → decrease (scroll down / Button-5)
        direction_down=False → increase (scroll up / Button-4)

        When ``log_mode=True`` a multiplicative step (``_LOG_FACTOR``) is used
        instead of the additive ``step`` so the scroll feels natural on a log axis.
        When the current value is below 1.0 in log mode a flat ±1.0 additive
        step is used in *both* directions to escape the sub-1 zone quickly;
        otherwise each log-mode tick would crawl (e.g. 0.5 → 0.561 → 0.630 …).
        """
        if log_mode:
            if current < 1.0:
                current = current - 1.0 if direction_down else current + 1.0
            else:
                current = current / _LOG_FACTOR if direction_down else current * _LOG_FACTOR
            current = max(min_limit, current)
            current = min(current, max_val * 0.999)
        else:
            current = current - step if direction_down else current + step
            current = max(min_limit, current)
            current = min(current, max_val - 1.0)
        if current <= 0:
            current = 0.1
        return round(current, 1)

    @staticmethod
    def clamp_max(current: float, step: float, direction_down: bool,
                  min_val: float, max_limit: float,
                  log_mode: bool = False) -> float:
        """Return a new validated max value after a scroll event.

        When ``log_mode=True`` a multiplicative step is used for values ≥ 1.
        Sub-1 values use the same ±1.0 additive escape as ``clamp_min`` so the
        max entry does not crawl when it crosses the 1-boundary.
        """
        if log_mode:
            if current < 1.0:
                current = current - 1.0 if direction_down else current + 1.0
            else:
                current = current / _LOG_FACTOR if direction_down else current * _LOG_FACTOR
            current = min(max_limit, current)
            current = max(current, min_val * 1.001)
        else:
            current = current - step if direction_down else current + step
            current = min(max_limit, current)
            current = max(current, min_val + 1.0)
        return round(current, 1)

    # ------------------------------------------------------------------
    # Range validation (focus-out / Return)
    # ------------------------------------------------------------------

    @staticmethod
    def validate_min(raw: str, max_raw: str,
                     hard_min: float | None = None) -> str | None:
        """Validate and format a min-range string.

        Returns the formatted string (``"N.N"``) if valid, else ``None``.
        Silently snaps to ``hard_min`` if the value is below it.
        """
        try:
            val = float(raw)
            if val <= 0:
                val = 0.1
            xmax = float(max_raw)
            if val >= xmax:
                val = xmax - 1.0
            if hard_min is not None:
                val = max(val, hard_min)
            return f"{val:.1f}"
        except (ValueError, TypeError):
            return None

    @staticmethod
    def validate_max(raw: str, min_raw: str,
                     hard_max: float | None = None) -> str | None:
        """Validate and format a max-range string.

        Silently snaps to ``hard_max`` if the value exceeds it.
        """
        try:
            val = float(raw)
            xmin = float(min_raw)
            if val <= xmin:
                val = xmin + 1.0
            if hard_max is not None:
                val = min(val, hard_max)
            return f"{val:.1f}"
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Render-options assembly
    # ------------------------------------------------------------------

    @staticmethod
    def build_render_options(
        w: int,
        h: int,
        *,
        xmin_raw: str = "",
        xmax_raw: str = "",
        ymin_raw: str = "",
        ymax_raw: str = "",
        logx: bool = False,
        logy: bool = False,
        xtitle: str = "",
        ytitle: str = "",
        title: str = "",
        show_markers: bool = True,
        peak_energies: list[float] | None = None,
    ) -> dict:
        """Assemble the options dict passed to ``HistogramRenderer``.

        All tkinter-Var extraction happens in the tab layer; this method
        receives already-converted Python primitives.

        When ``w`` and ``h`` are both 0 the ``target_width``, ``target_height``
        and ``priority`` keys are **omitted** from the result so that
        ``HistogramRenderer.render_into_label`` falls back to reading the
        actual label geometry — this ensures the rendered image fills the
        preview label with no blank white-space border.
        """
        options: dict = {"show_markers": show_markers}

        # Only include explicit target dimensions when the caller provides them.
        # Callers that want "fit the label" should pass w=0, h=0.
        if w > 0 and h > 0:
            options["target_width"] = int(w)
            options["target_height"] = int(h)
            options["priority"] = "height"

        try:
            if xmin_raw and xmax_raw:
                options["xmin"] = float(xmin_raw)
                options["xmax"] = float(xmax_raw)
        except (ValueError, TypeError):
            pass

        try:
            if ymin_raw and ymax_raw:
                options["ymin"] = float(ymin_raw)
                options["ymax"] = float(ymax_raw)
        except (ValueError, TypeError):
            pass

        if logx:
            options["logx"] = True
        if logy:
            options["logy"] = True

        if xtitle:
            options["xtitle"] = xtitle
        if ytitle:
            options["ytitle"] = ytitle
        if title:
            options["title"] = title

        if show_markers and peak_energies:
            options["markers"] = list(peak_energies)

        return options

    @staticmethod
    def compute_preview_size(win_w: int, win_h: int) -> tuple[int, int]:
        """Return ``(width, height)`` pixel targets for the histogram preview label.

        Width  ~ 80 % of window width  (min 160).
        Height ~ 50 % of window height (min 120).
        """
        w = int(max(160, win_w * 0.8))
        h = int(max(120, win_h * 0.5))
        return w, h

    @staticmethod
    def detect_scroll_direction(event) -> bool:
        """Return ``True`` if the scroll event represents a downward scroll.

        Handles both Windows/macOS (``event.delta``) and Linux
        (``event.num``) scroll events.  ``True`` means *decrease* (scroll
        down / ``Button-5`` / negative delta); ``False`` means *increase*.
        """
        return event.num == 5 or (hasattr(event, "delta") and event.delta < 0)


__all__ = ["HistogramControlsModule"]

"""Peak export feature: serialises peak lists to CSV and JSON.

Pure Python — no ROOT, no tkinter.  ``SaveManager`` delegates all peak
serialisation work to this feature so the module layer stays thin.
"""

from __future__ import annotations

import json
import os

from features.feature import Feature


class PeakExportFeature(Feature):
    """Serialises peak lists to CSV and/or JSON files."""

    name = "PeakExport"

    # Gaussian annotation constants
    _FWHM: float = 2.355
    _SQRT2PI: float = 2.506628

    def export_csv(
        self,
        peaks: list[dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
        fit_states: dict | None = None,
    ) -> str | None:
        """Write *peaks* to a CSV file.

        When *fit_states* is supplied a second section with fit results is
        appended to the same file.

        Args:
            peaks: List of peak dicts with ``energy``, ``counts``, ``source``.
            histogram_name: Informational label used in the file.
            filepath: Destination path (required).
            fit_states: Optional fit-state dict from ``FitModule``.

        Returns:
            *filepath* on success, ``None`` when *peaks* is empty.
        """
        if not peaks:
            return None
        if not filepath:
            raise ValueError("filepath is required")

        import csv

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Peak_Number", "Energy_keV", "Counts", "Source"])
            for i, peak in enumerate(peaks, 1):
                writer.writerow([
                    i,
                    f"{peak['energy']:.2f}",
                    f"{peak['counts']:.1f}" if peak.get("counts") is not None else "",
                    peak.get("source", ""),
                ])

            if fit_states:
                writer.writerow([])
                writer.writerow(["Fit Results"])
                writer.writerow([
                    "Fit_ID", "Fit_Function", "Energy_keV", "Width_keV",
                    "Chi2", "NDF", "Reduced_Chi2", "Status",
                    "FWHM_keV", "Centroid_keV", "Area",
                ])
                for fit_id, fs in sorted(fit_states.items()):
                    cached = fs.get("cached_results")
                    if cached is None or "error" in cached:
                        continue
                    fit_func = _fit_state_val(fs, "fit_func", "unknown")
                    energy   = _fit_state_val(fs, "energy", "")
                    width    = _fit_state_val(fs, "width", "")
                    chi2   = cached.get("chi2", "")
                    ndf    = cached.get("ndf", "")
                    reduced = chi2 / ndf if (ndf and ndf > 0) else ""
                    params = cached.get("parameters", [])
                    fwhm = centroid = area = ""
                    if (fit_func == "gaus" or fit_func.startswith("gaus+")) and len(params) >= 3:
                        fwhm = self._FWHM * params[2]
                        centroid = params[1]
                        area = params[0] * params[2] * self._SQRT2PI
                    writer.writerow([
                        fit_id, fit_func, energy, width,
                        f"{chi2:.6f}" if chi2 else "", ndf,
                        f"{reduced:.6f}" if reduced else "",
                        cached.get("status", ""),
                        f"{fwhm:.3f}" if fwhm else "",
                        f"{centroid:.3f}" if centroid else "",
                        f"{area:.1f}" if area else "",
                    ])

        return filepath

    def export_json(
        self,
        peaks: list[dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
        fit_states: dict | None = None,
    ) -> str | None:
        """Write *peaks* (and optionally fit results) to a JSON file.

        Args:
            peaks: List of peak dicts.
            histogram_name: Top-level label in the JSON document.
            filepath: Destination path (required).
            fit_states: Optional fit-state dict from ``FitModule``.

        Returns:
            *filepath* on success, ``None`` when *peaks* is empty.
        """
        if not peaks:
            return None
        if not filepath:
            raise ValueError("filepath is required")

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        export: dict = {
            "histogram": histogram_name,
            "peaks": [
                {
                    "peak_number": i,
                    "energy_keV": round(float(p["energy"]), 4),
                    "counts": (
                        round(float(p["counts"]), 2)
                        if p.get("counts") is not None else None
                    ),
                    "source": p.get("source", ""),
                }
                for i, p in enumerate(peaks, 1)
            ],
        }

        if fit_states:
            fits_section = []
            for fit_id, fs in sorted(fit_states.items()):
                cached = fs.get("cached_results")
                if cached is None or "error" in cached:
                    continue
                fit_func = _fit_state_val(fs, "fit_func", "unknown")
                params   = cached.get("parameters", [])
                errors   = cached.get("errors", [])
                chi2     = cached.get("chi2", 0)
                ndf      = cached.get("ndf", 0)
                entry: dict = {
                    "fit_id":       fit_id,
                    "fit_function": fit_func,
                    "energy_keV":   _fit_state_val(fs, "energy", None),
                    "width_keV":    _fit_state_val(fs, "width", None),
                    "chi2":         chi2,
                    "ndf":          ndf,
                    "reduced_chi2": chi2 / ndf if ndf > 0 else None,
                    "status":       cached.get("status", 0),
                    "parameters":   [
                        {
                            "index": i,
                            "value": p,
                            "error": errors[i] if i < len(errors) else 0,
                        }
                        for i, p in enumerate(params)
                    ],
                }
                is_gaus = fit_func == "gaus" or fit_func.startswith("gaus+")
                if is_gaus and len(params) >= 3:
                    entry["annotations"] = {
                        "fwhm_keV":     self._FWHM * params[2],
                        "centroid_keV": params[1],
                        "area":         params[0] * params[2] * self._SQRT2PI,
                    }
                elif fit_func in ("2gaus", "2gaus+pol1") and len(params) >= 6:
                    entry["annotations"] = {
                        "peak1": {
                            "fwhm_keV":     self._FWHM * params[2],
                            "centroid_keV": params[1],
                            "area":         params[0] * params[2] * self._SQRT2PI,
                        },
                        "peak2": {
                            "fwhm_keV":     self._FWHM * params[5],
                            "centroid_keV": params[4],
                            "area":         params[3] * params[5] * self._SQRT2PI,
                        },
                    }
                fits_section.append(entry)
            export["fits"] = fits_section

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(export, fh, indent=2)

        return filepath


# ---------------------------------------------------------------------------
# Module-level helper (used by both features and save_manager)
# ---------------------------------------------------------------------------

def _fit_state_val(fit_state: dict, key: str, default=""):
    """Extract a plain Python value from a fit state dict.

    Supports both the new ``FitModule`` plain-dict states (``"fit_func"``,
    ``"energy"``, ``"width"`` as native Python values) and legacy tkinter-Var
    based states (``"fit_func_var"``, ``"energy_var"``, ``"width_var"``).
    """
    val = fit_state.get(key)
    if val is not None:
        return val
    var = fit_state.get(f"{key}_var")
    if var is not None and hasattr(var, "get") and callable(var.get):
        try:
            return var.get()
        except Exception:
            pass
    return default


__all__ = ["PeakExportFeature", "_fit_state_val"]

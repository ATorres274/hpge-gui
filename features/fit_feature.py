"""Pure fitting computation feature.

Provides static helpers for histogram fitting via ROOT TF1.  No UI code and
no persistent state live here — the owning module (``modules.fit_module``)
delegates all ROOT computation and result formatting to this feature.
"""

from __future__ import annotations

import os
from contextlib import redirect_stdout, redirect_stderr

from features.feature import Feature


# Gaussian constants used in parameter estimation and result formatting.
_FWHM_TO_SIGMA: float = 2.355      # 2 * sqrt(2 * ln 2)  — converts FWHM to σ
_SQRT_2PI: float = 2.506628        # sqrt(2π)             — Gaussian normalisation

# ROOT TF1 formula strings for photopeak fit models.
# Compound models need explicit parameter-group indexing so ROOT builds
# the correct TF1.
_FIT_FORMULAS: dict[str, str] = {
    # Pure Gaussian — baseline photopeak model
    "gaus":       "gaus",
    # Gaussian + polynomial background
    "gaus+pol1":  "gaus(0)+pol1(3)",
    "gaus+pol2":  "gaus(0)+pol2(3)",
    # Gaussian + error-function step background (Compton-edge correction)
    "gaus+erf":   "gaus(0)+[3]*TMath::Erfc((x-[1])/(sqrt(2)*[2]))*0.5",
    # Double Gaussian — overlapping/doublet photopeaks
    "2gaus":      "gaus(0)+gaus(3)",
    "2gaus+pol1": "gaus(0)+gaus(3)+pol1(6)",
}

# All supported fit functions as an ordered list for UI dropdowns.
FIT_FUNCTIONS: list[str] = [
    "gaus",
    "gaus+pol1",
    "gaus+pol2",
    "gaus+erf",
    "2gaus",
    "2gaus+pol1",
]


class FitFeature(Feature):
    """Pure-computation feature for ROOT histogram fitting.

    All methods are static; the class is purely a namespace for fit-related
    pure functions so that ``FitModule`` can delegate computation without
    mixing ROOT operations into its UI code.
    """

    name = "Fit"

    # Parameter label strings shown in the controls row of each fit card.
    _PARAM_LABELS: dict[str, list[str]] = {
        "gaus":       ["Constant (p0)", "Mean (p1)", "Sigma (p2)"],
        "gaus+pol1":  ["Constant (p0)", "Mean (p1)", "Sigma (p2)",
                       "Bkg a0 (p3)", "Bkg a1 (p4)"],
        "gaus+pol2":  ["Constant (p0)", "Mean (p1)", "Sigma (p2)",
                       "Bkg a0 (p3)", "Bkg a1 (p4)", "Bkg a2 (p5)"],
        "gaus+erf":   ["Constant (p0)", "Mean (p1)", "Sigma (p2)",
                       "Step Amp (p3)"],
        "2gaus":      ["Const1 (p0)", "Mean1 (p1)", "Sigma1 (p2)",
                       "Const2 (p3)", "Mean2 (p4)", "Sigma2 (p5)"],
        "2gaus+pol1": ["Const1 (p0)", "Mean1 (p1)", "Sigma1 (p2)",
                       "Const2 (p3)", "Mean2 (p4)", "Sigma2 (p5)",
                       "Bkg a0 (p6)", "Bkg a1 (p7)"],
    }

    # Short parameter names used when displaying fit results.
    _PARAM_DISPLAY: dict[str, list[str]] = {
        "gaus":       ["Constant", "Mean", "Sigma"],
        "gaus+pol1":  ["Constant", "Mean", "Sigma", "Bkg a0", "Bkg a1"],
        "gaus+pol2":  ["Constant", "Mean", "Sigma", "Bkg a0", "Bkg a1", "Bkg a2"],
        "gaus+erf":   ["Constant", "Mean", "Sigma", "Step Amp"],
        "2gaus":      ["Const1", "Mean1", "Sigma1", "Const2", "Mean2", "Sigma2"],
        "2gaus+pol1": ["Const1", "Mean1", "Sigma1", "Const2", "Mean2", "Sigma2",
                       "Bkg a0", "Bkg a1"],
    }

    @staticmethod
    def get_param_labels(fit_func: str) -> list[str]:
        """Return UI parameter label strings for *fit_func*."""
        return list(FitFeature._PARAM_LABELS.get(fit_func, []))

    @staticmethod
    def get_param_display_names(fit_func: str) -> list[str]:
        """Return short parameter names used in the results panel."""
        return list(FitFeature._PARAM_DISPLAY.get(fit_func, []))

    @staticmethod
    def get_fit_formula(fit_func: str) -> str:
        """Return the ROOT TF1 formula string for *fit_func*.

        Compound photopeak models like ``"gaus+pol1"`` require explicit
        parameter-group indexing (e.g. ``"gaus(0)+pol1(3)"``).  Simple
        named ROOT functions (``"gaus"``, ``"expo"``, …) pass through
        unchanged.
        """
        return _FIT_FORMULAS.get(fit_func, fit_func)

    @staticmethod
    def get_fit_range(
        energy: float | None,
        width: float | None,
    ) -> tuple[float | None, float | None]:
        """Convert peak (energy, width) to a (xmin, xmax) fit window.

        Returns ``(None, None)`` when either value is missing or non-numeric.
        """
        try:
            if energy is None or width is None:
                return (None, None)
            e = float(energy)
            w = float(width)
            return (e - w / 2.0, e + w / 2.0)
        except (TypeError, ValueError):
            return (None, None)

    @staticmethod
    def default_fit_params(
        fit_func: str,
        hist,
        energy: float | None,
        width: float | None,
        xmin: float,
        xmax: float,
    ) -> list[float]:
        """Return sensible initial parameter guesses for *fit_func*.

        Scans ``[xmin, xmax]`` for the actual maximum bin to seed amplitude
        and centroid.  Estimates sigma from the half-maximum crossing points
        rather than a fixed fraction of the window width.

        Args:
            fit_func: One of gaus, gaus+pol1, gaus+pol2, gaus+erf.
            hist: ROOT TH1 histogram (used to estimate mean and peak height).
            energy: Peak location hint in keV (``None`` → use max-bin centre).
            width: Peak width hint in keV (``None`` → auto-estimate from FWHM).
            xmin: Left edge of fit range.
            xmax: Right edge of fit range.

        Returns:
            List of ``float`` initial parameter values.
        """
        # --- locate the peak bin within [xmin, xmax] -----------------------
        peak_height = 1.0
        peak_x = energy if energy is not None else (xmin + xmax) / 2.0

        if hist is not None and hasattr(hist, "FindBin"):
            try:
                b_lo = hist.FindBin(xmin)
                b_hi = hist.FindBin(xmax)
                if b_hi >= b_lo:
                    max_content = -1.0
                    max_bin = b_lo
                    for b in range(b_lo, b_hi + 1):
                        c = float(hist.GetBinContent(b))
                        if c > max_content:
                            max_content = c
                            max_bin = b
                    peak_height = max(max_content, 1.0)
                    # Prefer energy hint for mean; fall back to max-bin centre.
                    if energy is None:
                        peak_x = float(hist.GetBinCenter(max_bin))
            except Exception:
                pass

        # --- estimate sigma from FWHM or explicit width --------------------
        if width is not None and width > 0:
            sigma = float(width) / _FWHM_TO_SIGMA
        else:
            # Walk outward from peak_x to find half-maximum crossing.
            # Use range/8 as the conservative seed before the walk; this is
            # narrower than range/5 (old fallback) to avoid over-broad starts.
            sigma = max((xmax - xmin) / 8.0, 0.5)
            if hist is not None and hasattr(hist, "FindBin"):
                try:
                    half = peak_height / 2.0
                    center_bin = hist.FindBin(peak_x)
                    b_lo = hist.FindBin(xmin)
                    b_hi = hist.FindBin(xmax)
                    # Search left half-max
                    left_x = xmin
                    for b in range(center_bin, b_lo - 1, -1):
                        if float(hist.GetBinContent(b)) <= half:
                            left_x = float(hist.GetBinCenter(b))
                            break
                    # Search right half-max
                    right_x = xmax
                    for b in range(center_bin, b_hi + 1):
                        if float(hist.GetBinContent(b)) <= half:
                            right_x = float(hist.GetBinCenter(b))
                            break
                    fwhm_est = right_x - left_x
                    if fwhm_est > 0:
                        sigma = fwhm_est / _FWHM_TO_SIGMA
                except Exception:
                    pass
        sigma = max(sigma, 1e-6)

        if fit_func == "gaus":
            return [peak_height, peak_x, sigma]
        # Photopeak compound models: Gaussian params + background
        if fit_func == "gaus+pol1":
            return [peak_height, peak_x, sigma, 0.0, 0.0]
        if fit_func == "gaus+pol2":
            return [peak_height, peak_x, sigma, 0.0, 0.0, 0.0]
        if fit_func == "gaus+erf":
            # Step amplitude seeded at half the peak height
            return [peak_height, peak_x, sigma, max(peak_height * 0.5, 1.0)]
        # Double-Gaussian models: seed second peak offset by one sigma
        if fit_func == "2gaus":
            return [peak_height, peak_x, sigma,
                    peak_height * 0.5, peak_x + sigma, sigma]
        if fit_func == "2gaus+pol1":
            return [peak_height, peak_x, sigma,
                    peak_height * 0.5, peak_x + sigma, sigma,
                    0.0, 0.0]
        return []

    @staticmethod
    def clone_histogram(hist, name_suffix: str = "_fit_clone"):
        """Return a ROOT clone of *hist* for non-destructive fitting.

        Falls back to *hist* itself when cloning raises an exception.
        Returns ``None`` when *hist* is ``None``.
        """
        if hist is None:
            return None
        try:
            clone_name = (
                f"{hist.GetName()}{name_suffix}"
                if hasattr(hist, "GetName")
                else f"hist{name_suffix}"
            )
            return hist.Clone(clone_name)
        except Exception:
            return hist

    @staticmethod
    def perform_fit(
        root,
        hist_clone,
        fit_func: str,
        fit_id: int,
        fit_epoch: int,
        xmin: float,
        xmax: float,
        params: list[float],
        fixed_params: list[bool],
        fit_option: str,
        prev_func_obj=None,
    ) -> tuple[dict, object]:
        """Fit *hist_clone* using a ROOT TF1 function.

        All ROOT terminal output is suppressed.  The previous fit function
        object is removed from the histogram's function list before the new
        fit is performed so that multiple fits coexist cleanly on the same
        clone.

        Args:
            root: ROOT Python module.
            hist_clone: ROOT TH1 histogram to fit (should be a clone).
            fit_func: Function name accepted by TF1 (gaus, expo, …).
            fit_id: Unique identifier for this fit (used in TF1 naming).
            fit_epoch: Incrementing counter that guarantees unique TF1 names.
            xmin: Left edge of the fit window.
            xmax: Right edge of the fit window.
            params: Initial parameter guesses (empty → auto-generate via
                ``default_fit_params``).
            fixed_params: Bool flags parallel to *params*; ``True`` = fix that
                parameter during minimisation.
            fit_option: ROOT Fit option string; ``"S"`` is appended if absent.
            prev_func_obj: TF1 from a prior fit on this clone to remove first
                (may be ``None``).

        Returns:
            ``(cached_results_dict, new_tf1_object)`` where
            *cached_results_dict* is the output of ``_extract_results``.
        """
        if "S" not in fit_option:
            fit_option = fit_option + "S"

        prev_batch = root.gROOT.IsBatch()
        root.gROOT.SetBatch(True)
        try:
            with open(os.devnull, "w") as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    # Remove previous fit function from clone's function list.
                    fit_list = hist_clone.GetListOfFunctions()
                    if fit_list is not None and prev_func_obj is not None:
                        try:
                            fit_list.Remove(prev_func_obj)
                        except Exception:
                            pass
                        try:
                            root.gROOT.RecursiveRemove(prev_func_obj)
                        except Exception:
                            pass

                    fit_name = f"fit_{fit_func}_{fit_id}_{fit_epoch}"
                    formula = FitFeature.get_fit_formula(fit_func)
                    fit_obj = root.TF1(fit_name, formula, xmin, xmax)

                    if not params:
                        params = FitFeature.default_fit_params(
                            fit_func, hist_clone, None, None, xmin, xmax
                        )

                    for i, p in enumerate(params):
                        fit_obj.SetParameter(i, p)
                    for i, is_fixed in enumerate(fixed_params):
                        if is_fixed and i < len(params):
                            fit_obj.FixParameter(i, params[i])

                    fit_result = hist_clone.Fit(fit_obj, fit_option, "", xmin, xmax)

            cached = FitFeature._extract_results(fit_result, fit_obj)
            return cached, fit_obj
        finally:
            root.gROOT.SetBatch(prev_batch)

    @staticmethod
    def _extract_results(fit_result, func_obj) -> dict:
        """Extract fit results into a plain Python dict (no ROOT objects).

        Tries the TF1 function object first (most reliable across ROOT
        versions), then falls back to the TFitResultPtr.

        Returns a dict with keys ``chi2``, ``ndf``, ``status``,
        ``parameters``, ``errors`` on success, or ``{"error": <msg>}``
        on failure.
        """
        if func_obj is not None:
            try:
                npar = int(func_obj.GetNpar()) if hasattr(func_obj, "GetNpar") else 0
                params = [float(func_obj.GetParameter(i)) for i in range(npar)]
                errors = [float(func_obj.GetParError(i)) for i in range(npar)]
                chi2 = (
                    float(func_obj.GetChisquare())
                    if hasattr(func_obj, "GetChisquare")
                    else 0.0
                )
                ndf = int(func_obj.GetNDF()) if hasattr(func_obj, "GetNDF") else 0
                return {
                    "chi2": chi2,
                    "ndf": ndf,
                    "status": 0,
                    "parameters": params,
                    "errors": errors,
                }
            except Exception:
                pass

        if fit_result is None:
            return {"error": "Fit result is None"}

        try:
            result = (
                fit_result.Get() if hasattr(fit_result, "Get") else fit_result
            )
            if result is None:
                return {"error": "Fit result pointer is null"}
            status = int(result.Status())
            if status != 0:
                return {
                    "error": (
                        f"Fit failed with status {status}. "
                        "Try adjusting energy range or initial parameters."
                    ),
                }
            num_params = (
                len(result.Parameters()) if hasattr(result, "Parameters") else 0
            )
            return {
                "chi2": float(result.Chi2()),
                "ndf": int(result.Ndf()),
                "status": status,
                "parameters": list(result.Parameters()) if num_params > 0 else [],
                "errors": [float(result.ParError(i)) for i in range(num_params)],
            }
        except Exception as exc:
            return {"error": f"Failed to extract fit results: {exc}"}

    @staticmethod
    def format_fit_results(fit_func: str, fit_option: str, cached: dict) -> str:
        """Format *cached* fit results as a human-readable multi-line string.

        Args:
            fit_func: Fit function name (gaus, expo, …).
            fit_option: Fit option string used (for display only).
            cached: Dict produced by ``_extract_results`` / ``perform_fit``.

        Returns:
            Multi-line string suitable for a read-only Text widget.
        """
        if "error" in cached:
            return cached["error"]

        chi2 = cached.get("chi2", 0.0)
        ndf = cached.get("ndf", 0)
        status = cached.get("status", -1)
        parameters = cached.get("parameters", [])
        errors = cached.get("errors", [])

        lines = [
            f"Fit Function: {fit_func}",
            f"Fit Options: {fit_option}",
            f"Chi-square: {chi2:.6f}",
            f"NDF: {ndf}",
            f"Reduced Chi-square: {chi2 / ndf if ndf > 0 else 'N/A'}",
            f"Status: {status}",
            "",
            "Parameters:",
        ]

        names = FitFeature.get_param_display_names(fit_func)
        for i, param in enumerate(parameters):
            error = errors[i] if i < len(errors) else 0.0
            name = names[i] if i < len(names) else f"p[{i}]"
            lines.append(f"  {name} = {param:.6f} ± {error:.6f}")

        if fit_func == "gaus" or fit_func.startswith("gaus+"):
            if len(parameters) >= 3:
                mean = parameters[1]
                sigma = parameters[2]
                fwhm = _FWHM_TO_SIGMA * sigma
                constant = parameters[0]
                area = constant * sigma * _SQRT_2PI
                lines += [
                    "",
                    "Peak Annotations:",
                    f"  FWHM: {fwhm:.3f} keV",
                    f"  Centroid: {mean:.3f} keV",
                    f"  Area: {area:.1f}",
                ]
        elif fit_func in ("2gaus", "2gaus+pol1"):
            if len(parameters) >= 6:
                for i, label in enumerate(("Peak 1", "Peak 2")):
                    c, m, s = parameters[i * 3], parameters[i * 3 + 1], parameters[i * 3 + 2]
                    fwhm = _FWHM_TO_SIGMA * s
                    area = c * s * _SQRT_2PI
                    if i == 0:
                        lines += ["", "Peak Annotations:"]
                    lines += [
                        f"  {label}  Centroid: {m:.3f} keV,"
                        f"  FWHM: {fwhm:.3f} keV,"
                        f"  Area: {area:.1f}",
                    ]

        return "\n".join(lines)

    @staticmethod
    def format_fit_results_short(fit_func: str, cached: dict) -> str:
        """Return a compact ~5-line summary for the TCanvas TPaveText overlay.

        Shows only the most useful quantities: chi2/ndf, centroid, sigma/FWHM,
        and area for a Gaussian fit.  Intended to be placed in a corner without
        covering the histogram data.
        """
        if "error" in cached:
            return cached["error"]

        chi2 = cached.get("chi2", 0.0)
        ndf  = cached.get("ndf", 0)
        parameters = cached.get("parameters", [])
        errors     = cached.get("errors", [])

        red_chi2 = (chi2 / ndf) if ndf > 0 else float("nan")
        lines = [f"#chi^{{2}} / ndf = {red_chi2:.3f}"]

        if fit_func in ("gaus", "gaus+pol0", "gaus+pol1") and len(parameters) >= 3:
            mean    = parameters[1]
            sigma   = parameters[2]
            mean_e  = errors[1] if len(errors) > 1 else 0.0
            sigma_e = errors[2] if len(errors) > 2 else 0.0
            fwhm    = _FWHM_TO_SIGMA * sigma
            const   = parameters[0]
            area    = const * sigma * _SQRT_2PI
            lines += [
                f"Mean  = {mean:.3f} #pm {mean_e:.3f}",
                f"#sigma    = {sigma:.3f} #pm {sigma_e:.3f}",
                f"FWHM  = {fwhm:.3f}",
                f"Area  = {area:.0f}",
            ]
        elif fit_func in ("2gaus", "2gaus+pol1") and len(parameters) >= 6:
            for i, label in enumerate(("P1", "P2")):
                m = parameters[i * 3 + 1]
                s = parameters[i * 3 + 2]
                fwhm = _FWHM_TO_SIGMA * s
                lines.append(f"{label}: {m:.3f}  FWHM={fwhm:.3f}")
        else:
            names = FitFeature.get_param_display_names(fit_func)
            for i, p in enumerate(parameters[:4]):
                e    = errors[i] if i < len(errors) else 0.0
                name = names[i] if i < len(names) else f"p{i}"
                lines.append(f"{name} = {p:.4g} #pm {e:.3g}")

        return "\n".join(lines)

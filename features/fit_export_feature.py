"""Fit export feature: serialises fit results to CSV, JSON, and multi-page PDF.

Uses ROOT for the PDF report but never imports tkinter — that boundary belongs
to the tab-manager layer.  ``SaveManager`` delegates all fit serialisation and
PDF rendering work here so the module stays thin.
"""

from __future__ import annotations

import json
import os
from contextlib import redirect_stdout, redirect_stderr

from features.feature import Feature
from features.fit_feature import FitFeature
from features.peak_export_feature import _fit_state_val


# Distinct ROOT colour indices for overlaid fit curves
_FIT_COLORS: list[int] = [2, 4, 8, 6, 7, 3, 9, 46, 30]


class FitExportFeature(Feature):
    """Serialises fit results and generates the multi-page PDF fit report."""

    name = "FitExport"

    _FWHM: float = 2.355
    _SQRT2PI: float = 2.506628

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_csv(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        """Write all completed fit results to a CSV file.

        Args:
            fit_states: ``{fit_id: state}`` dict from ``FitModule``.
            histogram_name: Informational label.
            filepath: Destination path (required).

        Returns:
            *filepath* on success, ``None`` when *fit_states* is empty.
        """
        if not fit_states:
            return None
        if not filepath:
            raise ValueError("filepath is required")

        import csv

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "Fit_ID", "Fit_Function", "Energy_keV", "Width_keV",
                "Chi2", "NDF", "Reduced_Chi2", "Status",
                "Parameters", "Errors",
                "FWHM_keV", "Centroid_keV", "Area",
            ])
            for fit_id, fit_state in sorted(fit_states.items()):
                cached = fit_state.get("cached_results")
                if cached is None or "error" in cached:
                    continue
                fit_func = _fit_state_val(fit_state, "fit_func", "unknown")
                energy   = _fit_state_val(fit_state, "energy", "")
                width    = _fit_state_val(fit_state, "width", "")
                chi2   = cached.get("chi2", "")
                ndf    = cached.get("ndf", "")
                reduced = chi2 / ndf if (ndf and ndf > 0) else ""
                status  = cached.get("status", "")
                params  = cached.get("parameters", [])
                errors  = cached.get("errors", [])
                fwhm = centroid = area = ""
                if (fit_func == "gaus" or fit_func.startswith("gaus+")) and len(params) >= 3:
                    fwhm     = self._FWHM * params[2]
                    centroid = params[1]
                    area     = params[0] * params[2] * self._SQRT2PI
                writer.writerow([
                    fit_id, fit_func, energy, width,
                    f"{chi2:.6f}" if chi2 else "", ndf,
                    f"{reduced:.6f}" if reduced else "",
                    status,
                    "; ".join(f"{p:.6f}" for p in params),
                    "; ".join(f"{e:.6f}" for e in errors),
                    f"{fwhm:.3f}" if fwhm else "",
                    f"{centroid:.3f}" if centroid else "",
                    f"{area:.1f}" if area else "",
                ])
        return filepath

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_json(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        """Write all completed fit results to a JSON file.

        Args:
            fit_states: ``{fit_id: state}`` dict from ``FitModule``.
            histogram_name: Top-level label in the JSON document.
            filepath: Destination path (required).

        Returns:
            *filepath* on success, ``None`` when *fit_states* is empty.
        """
        if not fit_states:
            return None
        if not filepath:
            raise ValueError("filepath is required")

        import datetime

        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        export_data: dict = {
            "histogram": histogram_name,
            # Local time is intentional — this is a human-readable label for
            # the analyst; machine consumers should convert as needed.
            "export_timestamp": datetime.datetime.now().isoformat(),
            "fits": [],
        }
        for fit_id, fit_state in sorted(fit_states.items()):
            cached = fit_state.get("cached_results")
            if cached is None:
                continue
            fit_func = _fit_state_val(fit_state, "fit_func", "unknown")
            energy   = _fit_state_val(fit_state, "energy", "")
            width    = _fit_state_val(fit_state, "width", "")
            fit_data: dict = {
                "fit_id":       fit_id,
                "fit_function": fit_func,
                "energy_keV":   float(energy) if energy else None,
                "width_keV":    float(width) if width else None,
            }
            if "error" in cached:
                fit_data["error"] = cached["error"]
            else:
                chi2   = cached.get("chi2", 0)
                ndf    = cached.get("ndf", 0)
                params = cached.get("parameters", [])
                errors = cached.get("errors", [])
                fit_data.update({
                    "chi2":         chi2,
                    "ndf":          ndf,
                    "reduced_chi2": chi2 / ndf if ndf > 0 else None,
                    "status":       cached.get("status", 0),
                    "parameters": [
                        {
                            "index": i,
                            "value": p,
                            "error": errors[i] if i < len(errors) else 0,
                        }
                        for i, p in enumerate(params)
                    ],
                })
                is_gaus = fit_func == "gaus" or fit_func.startswith("gaus+")
                if is_gaus and len(params) >= 3:
                    fit_data["annotations"] = {
                        "fwhm_keV":     self._FWHM * params[2],
                        "centroid_keV": params[1],
                        "area":         params[0] * params[2] * self._SQRT2PI,
                    }
                elif fit_func == "landau" and len(params) >= 3:
                    fit_data["annotations"] = {
                        "most_probable_value_keV": params[1],
                        "width_keV":               params[2],
                    }
            export_data["fits"].append(fit_data)

        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(export_data, fh, indent=2)

        return filepath

    # ------------------------------------------------------------------
    # Multi-page PDF report
    # ------------------------------------------------------------------

    def export_report_pdf(
        self,
        root,
        hist,
        fit_states: dict[int, dict],
        directory: str,
        name: str,
    ) -> str | None:
        """Generate a multi-page PDF fit report via ROOT.

        Page layout:
            1. **Title page** — histogram name, generation date, fit summary.
            2. **Overview page** — full unzoomed spectrum with all fit curves
               in distinct colours plus a ``TLegend`` showing each fit label
               and ``#chi^{2}/ndf`` value.
            3. **One page per fit** — histogram zoomed to the fit window with
               the fit curve drawn and a ``TPaveText`` overlay of fit results.

        Args:
            root: ROOT Python module.
            hist: Original ROOT TH1 histogram.
            fit_states: ``{fit_id: state}`` dict from ``FitModule``.
            directory: Output directory path.
            name: Base filename stem (without extension).

        Returns:
            Path to the saved PDF, or ``None`` when nothing was exported.
        """
        if not fit_states or hist is None or root is None:
            return None

        completed = [
            (fid, state)
            for fid, state in sorted(fit_states.items())
            if state.get("has_fit") and state.get("cached_results") is not None
        ]
        if not completed:
            return None

        import datetime

        hist_title = ""
        try:
            hist_title = str(hist.GetTitle()) or str(hist.GetName())
        except Exception:
            hist_title = name

        pdf_path = os.path.join(directory, f"{name}_fit_report.pdf")
        prev_batch = root.gROOT.IsBatch()
        root.gROOT.SetBatch(True)
        try:
            with open(os.devnull, "w") as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    old_stdout = os.dup(1)
                    old_stderr = os.dup(2)
                    try:
                        os.dup2(devnull.fileno(), 1)
                        os.dup2(devnull.fileno(), 2)

                        canvas = root.TCanvas(
                            "_pyhpge_fit_report", "Fit Report", 1200, 600
                        )
                        canvas.Print(f"{pdf_path}[")  # open PDF

                        # ── Page 1: Title page ────────────────────────────
                        self._draw_title_page(
                            root, canvas, hist_title, completed,
                            # Local time is intentional — this is a human-readable
                            # label on the cover page, not a machine-parsed timestamp.
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        )
                        canvas.Print(pdf_path)

                        # ── Page 2: Overview ──────────────────────────────
                        self._draw_overview_page(
                            root, canvas, hist, hist_title,
                            completed, fit_states, pdf_path,
                        )

                        # ── Pages 3…N: one per fit ────────────────────────
                        for fit_idx, (fit_id, state) in enumerate(completed):
                            self._draw_fit_page(
                                root, canvas, hist, fit_id, fit_idx,
                                state, pdf_path,
                            )

                        canvas.Print(f"{pdf_path}]")  # close PDF
                        try:
                            canvas.Close()
                        except Exception:
                            pass

                    finally:
                        os.dup2(old_stdout, 1)
                        os.dup2(old_stderr, 2)
                        os.close(old_stdout)
                        os.close(old_stderr)
        finally:
            root.gROOT.SetBatch(prev_batch)

        return pdf_path if os.path.isfile(pdf_path) else None

    # ------------------------------------------------------------------
    # Private page-drawing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_title_page(root, canvas, hist_title, completed, date_str) -> None:
        canvas.Clear()
        canvas.SetFillColor(0)
        canvas.SetBorderMode(0)
        try:
            canvas.SetLogy(0)
        except Exception:
            pass

        pave = root.TPaveText(0.05, 0.10, 0.95, 0.90, "NDC")
        pave.SetFillColor(0)
        pave.SetBorderSize(0)
        pave.SetTextAlign(22)  # centred

        def _add(text, size, font):
            try:
                t = pave.AddText(text)
                t.SetTextSize(size)
                t.SetTextFont(font)
            except Exception:
                pave.AddText(text)

        _add("Fit Report",              0.10, 62)   # bold Helvetica
        pave.AddText(" ")
        _add(f"Histogram:  {hist_title}", 0.055, 42)
        _add(f"Generated:  {date_str}",   0.045, 42)
        pave.AddText(" ")
        _add(f"Completed fits:  {len(completed)}", 0.050, 42)
        for fid, state in completed:
            energy  = state.get("energy")
            ff      = state.get("fit_func", "gaus")
            label   = f"  Fit {fid}:  {ff}"
            if energy is not None:
                label += f"  @ {float(energy):.1f} keV"
            _add(label, 0.038, 42)

        pave.Draw()
        canvas.Modified()
        canvas.Update()

    @staticmethod
    def _draw_overview_page(
        root, canvas, hist, hist_title,
        completed, fit_states, pdf_path,
    ) -> None:
        canvas.Clear()
        canvas.SetLeftMargin(0.08)
        canvas.SetRightMargin(0.04)
        canvas.SetTopMargin(0.08)
        canvas.SetBottomMargin(0.12)
        try:
            canvas.SetLogy(1)
        except Exception:
            pass

        h_overview = None
        drawn: list[tuple[int, object, int]] = []  # (fit_id, func_obj, color)
        try:
            h_overview = hist.Clone("_fit_report_overview")
            if hasattr(h_overview, "SetDirectory"):
                h_overview.SetDirectory(0)
            xax = h_overview.GetXaxis() if hasattr(h_overview, "GetXaxis") else None
            if xax is not None:
                xax.UnZoom()
            h_overview.SetTitle(f"{hist_title} — all fits")
            h_overview.Draw("HIST")

            for i, (fid, state) in enumerate(completed):
                func_obj = state.get("fit_func_obj")
                if func_obj is None:
                    continue
                try:
                    color = _FIT_COLORS[i % len(_FIT_COLORS)]
                    func_obj.SetLineColor(color)
                    func_obj.SetLineWidth(2)
                    func_obj.Draw("same")
                    drawn.append((fid, func_obj, color))
                except Exception:
                    pass
        except Exception:
            pass

        # TLegend: colour line + label + χ²/ndf per fit
        if drawn:
            try:
                n = len(drawn)
                leg_y2 = 0.90
                leg_y1 = max(0.50, leg_y2 - 0.06 * (n + 1))
                legend = root.TLegend(0.52, leg_y1, 0.97, leg_y2)
                legend.SetHeader(f"{hist_title} — fit summary", "C")
                legend.SetFillColor(0)
                legend.SetFillStyle(1001)
                legend.SetBorderSize(1)
                legend.SetTextFont(42)
                legend.SetTextSize(0.028)
                for fid, func_obj, _color in drawn:
                    state    = fit_states[fid]
                    fit_func = state.get("fit_func", "gaus")
                    energy   = state.get("energy")
                    cached   = state.get("cached_results", {})
                    chi2     = float(cached.get("chi2", 0.0))
                    ndf      = int(cached.get("ndf", 0))
                    red_chi2 = chi2 / ndf if ndf > 0 else None
                    chi2_str = f"{red_chi2:.3f}" if red_chi2 is not None else "N/A"
                    label = (
                        f"Fit {fid}: {fit_func}"
                        + (f" @ {float(energy):.1f} keV" if energy is not None else "")
                        + f"   #chi^{{2}}/ndf = {chi2_str}"
                    )
                    legend.AddEntry(func_obj, label, "l")
                legend.Draw()
            except Exception:
                pass

        canvas.Modified()
        canvas.Update()
        canvas.Print(pdf_path)

        if h_overview is not None:
            try:
                h_overview.Delete()
            except Exception:
                pass

    def _draw_fit_page(
        self, root, canvas, hist, fit_id, fit_idx, state, pdf_path,
    ) -> None:
        canvas.Clear()
        canvas.SetLeftMargin(0.08)
        canvas.SetRightMargin(0.04)
        canvas.SetTopMargin(0.08)
        canvas.SetBottomMargin(0.12)
        try:
            canvas.SetLogy(1)
        except Exception:
            pass

        energy       = state.get("energy")
        width        = state.get("width") or 20.0
        fit_func     = state.get("fit_func", "gaus")
        fit_options  = state.get("fit_options", "SQ")
        cached       = state.get("cached_results", {})
        fit_func_obj = state.get("fit_func_obj")

        # Compute zoomed window
        try:
            if energy is not None:
                xmin = float(energy) - float(width) / 2.0
                xmax = float(energy) + float(width) / 2.0
            else:
                xax  = hist.GetXaxis() if hasattr(hist, "GetXaxis") else None
                xmin = float(xax.GetXmin()) if xax else 0.0
                xmax = float(xax.GetXmax()) if xax else 1000.0
        except Exception:
            xmin, xmax = 0.0, 1000.0

        h_page = None
        try:
            h_page = hist.Clone(f"_fit_report_h_{fit_id}")
            if hasattr(h_page, "SetDirectory"):
                h_page.SetDirectory(0)
            xax_page = h_page.GetXaxis() if hasattr(h_page, "GetXaxis") else None
            if xax_page is not None:
                xax_page.SetRangeUser(xmin, xmax)
            page_title = (
                f"Fit {fit_id}  [{fit_func}]"
                + (f"  —  {float(energy):.1f} keV" if energy is not None else "")
            )
            h_page.SetTitle(page_title)
            h_page.Draw("HIST")

            if fit_func_obj is not None:
                try:
                    fit_func_obj.SetRange(xmin, xmax)
                    fit_func_obj.SetLineColor(_FIT_COLORS[fit_idx % len(_FIT_COLORS)])
                    fit_func_obj.SetLineWidth(2)
                    fit_func_obj.Draw("same")
                except Exception:
                    pass
        except Exception:
            pass

        # Fit results TPaveText overlay in the upper-right
        try:
            results_text = FitFeature.format_fit_results(fit_func, fit_options, cached)
        except Exception:
            results_text = str(cached)

        try:
            pave = root.TPaveText(0.50, 0.42, 0.97, 0.92, "NDC")
            pave.SetFillColor(0)
            pave.SetFillStyle(1001)
            pave.SetBorderSize(1)
            pave.SetTextAlign(12)   # left-aligned
            pave.SetTextFont(42)    # Helvetica
            pave.SetTextSize(0.030)
            for line in results_text.split("\n"):
                pave.AddText(line if line.strip() else " ")
            pave.Draw()
        except Exception:
            pass

        canvas.Modified()
        canvas.Update()
        canvas.Print(pdf_path)

        if h_page is not None:
            try:
                h_page.Delete()
            except Exception:
                pass


__all__ = ["FitExportFeature"]

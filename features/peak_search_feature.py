"""Combined peak search feature: automatic + manual handlers.

Provides `PeakSearchAutomatic` (TSpectrum wrapper) and
`PeakSearchManual` (manual peak helper) for peak handling.
"""

from __future__ import annotations

from features.feature import Feature
from typing import List


class PeakSearchAutomatic(Feature):
    name = "Automatic Peak Finder"

    @staticmethod
    def find_peaks(app, hist) -> List[dict]:
        try:
            root = getattr(app, "ROOT", None)
            if root is None:
                import ROOT  # type: ignore
                root = ROOT
        except Exception:
            return []

        try:
            prev_batch = root.gROOT.IsBatch()
            root.gROOT.SetBatch(True)
            try:
                spectrum = root.TSpectrum()
                n = spectrum.Search(hist, 3, "")
                peaks: List[dict] = []
                for i in range(n):
                    energy = float(spectrum.GetPositionX()[i])
                    counts = float(hist.GetBinContent(hist.FindBin(energy)))
                    peaks.append({"energy": energy, "counts": counts, "source": "automatic"})
                peaks.sort(key=lambda p: p["energy"])
                return peaks
            finally:
                root.gROOT.SetBatch(prev_batch)
        except Exception:
            return []


class PeakSearchManual(Feature):
    name = "Manual Peak Finder"

    @staticmethod
    def make_manual_peak(value: float, hist) -> dict:
        counts = None
        if hist is not None:
            try:
                counts = float(hist.GetBinContent(hist.FindBin(value)))
            except Exception:
                counts = None
        return {"energy": float(value), "counts": counts, "source": "manual"}


__all__ = ["PeakSearchAutomatic", "PeakSearchManual"]

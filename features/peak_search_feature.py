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
    def find_peaks(
        app,
        hist,
        sigma: float = 3.0,
        energy_min: float | None = None,
        energy_max: float | None = None,
        threshold_counts: float = 0.0,
    ) -> List[dict]:
        """Find peaks in *hist* using ROOT TSpectrum.

        Args:
            app: Application object (used to access ROOT module).
            hist: ROOT TH1 histogram.
            sigma: TSpectrum search resolution (default 3).  Higher values
                merge nearby peaks; lower values find more peaks.
            energy_min: Minimum energy (keV) to include — peaks below this
                value are discarded after search.  ``None`` = no lower bound.
            energy_max: Maximum energy (keV) to include — peaks above this
                value are discarded.  ``None`` = no upper bound.
            threshold_counts: Minimum bin content a peak must have to be
                included.  Useful for suppressing low-intensity noise peaks
                above a Compton edge or at high energies.  Default is 0
                (no minimum).

        Returns:
            Sorted list of ``{"energy": float, "counts": float, "source": "automatic"}``
            dicts, filtered to the requested energy window and count threshold.
        """
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
                n = spectrum.Search(hist, float(sigma), "")
                # TSpectrum may attach a TPolyMarker (markers) to the
                # histogram's function list. Remove any such objects so
                # we don't rely on ROOT's drawing — rendering should be
                # handled centrally by our RendererFeature.
                try:
                    func_list = None
                    if hasattr(hist, "GetListOfFunctions"):
                        func_list = hist.GetListOfFunctions()
                    if func_list is not None:
                        to_remove = []
                        for j in range(func_list.GetSize()):
                            try:
                                obj = func_list.At(j)
                                if obj and obj.ClassName() == "TPolyMarker":
                                    to_remove.append(obj)
                            except Exception:
                                pass
                        for obj in to_remove:
                            try:
                                func_list.Remove(obj)
                            except Exception:
                                pass
                except Exception:
                    pass
                peaks: List[dict] = []
                # Parameters for local background test: number of bins taken
                # on each side of the candidate peak and sigma threshold.
                BG_SIDE_BINS = 5
                BG_SIGMA_THRESHOLD = 3.0

                for i in range(n):
                    energy = float(spectrum.GetPositionX()[i])
                    peak_bin = hist.FindBin(energy)
                    counts = float(hist.GetBinContent(peak_bin))

                    # Energy window filter
                    if energy_min is not None and energy < energy_min:
                        continue
                    if energy_max is not None and energy > energy_max:
                        continue

                    # Minimum count threshold
                    if counts < threshold_counts:
                        continue

                    # Estimate local background using BG_SIDE_BINS on each side
                    nbins = hist.GetNbinsX()
                    bg_values: list[float] = []
                    # left side
                    for b in range(max(1, peak_bin - BG_SIDE_BINS), peak_bin):
                        try:
                            bg_values.append(float(hist.GetBinContent(b)))
                        except Exception:
                            pass
                    # right side
                    for b in range(peak_bin + 1, min(nbins + 1, peak_bin + BG_SIDE_BINS + 1)):
                        try:
                            bg_values.append(float(hist.GetBinContent(b)))
                        except Exception:
                            pass

                    # If we have background samples, require the peak to be
                    # significantly above background (BG_SIGMA_THRESHOLD * sqrt(bg)).
                    if bg_values:
                        bg_avg = float(sum(bg_values)) / float(len(bg_values))
                        # Poisson-like noise estimate; enforce a minimum noise floor
                        bg_noise = max(1.0, bg_avg ** 0.5)
                        if counts <= bg_avg + BG_SIGMA_THRESHOLD * bg_noise:
                            # Peak is consistent with background — ignore it.
                            continue

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

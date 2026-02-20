"""Unit tests for features.fit_feature.FitFeature and modules.fit_module.FitModule.

These tests cover the pure-computation feature and the domain module.
No ROOT or tkinter installation is required.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch, call

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Stub ROOT before any project imports touch it.
_MOCK_ROOT = MagicMock()
sys.modules.setdefault("ROOT", _MOCK_ROOT)

import unittest

from features.fit_feature import FitFeature


# ---------------------------------------------------------------------------
# FitFeature.get_param_labels
# ---------------------------------------------------------------------------

class TestGetParamLabels(unittest.TestCase):

    def test_gaus_returns_three_labels(self):
        labels = FitFeature.get_param_labels("gaus")
        self.assertEqual(len(labels), 3)
        self.assertIn("Constant", labels[0])
        self.assertIn("Mean", labels[1])
        self.assertIn("Sigma", labels[2])

    def test_gaus_pol1_returns_five_labels(self):
        labels = FitFeature.get_param_labels("gaus+pol1")
        self.assertEqual(len(labels), 5)
        self.assertIn("Bkg", labels[3])

    def test_gaus_pol2_returns_six_labels(self):
        labels = FitFeature.get_param_labels("gaus+pol2")
        self.assertEqual(len(labels), 6)

    def test_gaus_erf_returns_four_labels(self):
        labels = FitFeature.get_param_labels("gaus+erf")
        self.assertEqual(len(labels), 4)
        self.assertIn("Step", labels[3])

    def test_2gaus_returns_six_labels(self):
        labels = FitFeature.get_param_labels("2gaus")
        self.assertEqual(len(labels), 6)
        self.assertIn("1", labels[0])
        self.assertIn("2", labels[3])

    def test_2gaus_pol1_returns_eight_labels(self):
        labels = FitFeature.get_param_labels("2gaus+pol1")
        self.assertEqual(len(labels), 8)

    def test_unknown_function_returns_empty(self):
        self.assertEqual(FitFeature.get_param_labels("unknown_func"), [])

    def test_returns_copy_not_reference(self):
        """Mutating the returned list must not affect the class-level dict."""
        labels = FitFeature.get_param_labels("gaus")
        labels.clear()
        self.assertEqual(len(FitFeature.get_param_labels("gaus")), 3)


# ---------------------------------------------------------------------------
# FitFeature.get_param_display_names
# ---------------------------------------------------------------------------

class TestGetParamDisplayNames(unittest.TestCase):

    def test_gaus_display_names(self):
        names = FitFeature.get_param_display_names("gaus")
        self.assertEqual(names, ["Constant", "Mean", "Sigma"])

    def test_gaus_pol1_display_names(self):
        names = FitFeature.get_param_display_names("gaus+pol1")
        self.assertEqual(names, ["Constant", "Mean", "Sigma", "Bkg a0", "Bkg a1"])

    def test_2gaus_display_names(self):
        names = FitFeature.get_param_display_names("2gaus")
        self.assertEqual(len(names), 6)

    def test_unknown_returns_empty(self):
        self.assertEqual(FitFeature.get_param_display_names("bad"), [])


# ---------------------------------------------------------------------------
# FitFeature.get_fit_range
# ---------------------------------------------------------------------------

class TestGetFitRange(unittest.TestCase):

    def test_symmetric_range(self):
        xmin, xmax = FitFeature.get_fit_range(100.0, 20.0)
        self.assertAlmostEqual(xmin, 90.0)
        self.assertAlmostEqual(xmax, 110.0)

    def test_none_energy_returns_none_none(self):
        self.assertEqual(FitFeature.get_fit_range(None, 10.0), (None, None))

    def test_none_width_returns_none_none(self):
        self.assertEqual(FitFeature.get_fit_range(100.0, None), (None, None))

    def test_both_none_returns_none_none(self):
        self.assertEqual(FitFeature.get_fit_range(None, None), (None, None))

    def test_non_numeric_energy_returns_none_none(self):
        self.assertEqual(FitFeature.get_fit_range("abc", 10.0), (None, None))

    def test_non_numeric_width_returns_none_none(self):
        self.assertEqual(FitFeature.get_fit_range(100.0, "xyz"), (None, None))

    def test_zero_width_returns_equal_endpoints(self):
        xmin, xmax = FitFeature.get_fit_range(100.0, 0.0)
        self.assertAlmostEqual(xmin, 100.0)
        self.assertAlmostEqual(xmax, 100.0)

    def test_string_numbers_are_coerced(self):
        xmin, xmax = FitFeature.get_fit_range("200.0", "40.0")
        self.assertAlmostEqual(xmin, 180.0)
        self.assertAlmostEqual(xmax, 220.0)


# ---------------------------------------------------------------------------
# FitFeature.default_fit_params
# ---------------------------------------------------------------------------

class TestDefaultFitParams(unittest.TestCase):

    def _make_hist(self, mean=100.0, bin_content=1000.0):
        hist = MagicMock()
        hist.GetMean.return_value = mean
        hist.FindBin.return_value = 50
        hist.GetBinContent.return_value = bin_content
        return hist

    def test_gaus_returns_three_params(self):
        params = FitFeature.default_fit_params("gaus", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 3)

    def test_gaus_pol1_returns_five_params(self):
        params = FitFeature.default_fit_params("gaus+pol1", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 5)
        self.assertAlmostEqual(params[3], 0.0)  # background a0
        self.assertAlmostEqual(params[4], 0.0)  # background a1

    def test_gaus_pol2_returns_six_params(self):
        params = FitFeature.default_fit_params("gaus+pol2", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 6)

    def test_gaus_erf_returns_four_params(self):
        params = FitFeature.default_fit_params("gaus+erf", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 4)
        self.assertGreater(params[3], 0.0)  # step amplitude > 0

    def test_2gaus_returns_six_params(self):
        params = FitFeature.default_fit_params("2gaus", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 6)

    def test_2gaus_pol1_returns_eight_params(self):
        params = FitFeature.default_fit_params("2gaus+pol1", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 8)

    def test_unknown_returns_empty(self):
        params = FitFeature.default_fit_params("custom_func", self._make_hist(), None, None, 0.0, 100.0)
        self.assertEqual(params, [])

    def test_gaus_sigma_uses_width(self):
        params = FitFeature.default_fit_params("gaus", self._make_hist(), 100.0, 23.55, 90.0, 110.0)
        # sigma = width / 2.355 ≈ 10.0
        self.assertAlmostEqual(params[2], 10.0, places=2)

    def test_none_energy_uses_hist_mean(self):
        hist = self._make_hist(mean=250.0)
        params = FitFeature.default_fit_params("gaus", hist, None, 20.0, 200.0, 300.0)
        # Mean param should be close to histogram mean (250.0)
        self.assertAlmostEqual(params[1], 250.0)

    def test_zero_or_none_width_auto_estimated(self):
        params = FitFeature.default_fit_params("gaus", self._make_hist(), 100.0, None, 90.0, 110.0)
        # width = (110-90)/5 = 4.0  → sigma = 4.0/2.355
        self.assertGreater(params[2], 0)

    def test_hist_none_still_returns_params(self):
        params = FitFeature.default_fit_params("gaus", None, 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 3)


# ---------------------------------------------------------------------------
# FitFeature.clone_histogram
# ---------------------------------------------------------------------------

class TestCloneHistogram(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(FitFeature.clone_histogram(None))

    def test_successful_clone(self):
        hist = MagicMock()
        hist.GetName.return_value = "test_hist"
        clone = MagicMock()
        hist.Clone.return_value = clone
        result = FitFeature.clone_histogram(hist)
        hist.Clone.assert_called_once_with("test_hist_fit_clone")
        self.assertIs(result, clone)

    def test_clone_failure_returns_original(self):
        hist = MagicMock()
        hist.GetName.return_value = "bad_hist"
        hist.Clone.side_effect = RuntimeError("clone failed")
        result = FitFeature.clone_histogram(hist)
        self.assertIs(result, hist)

    def test_custom_suffix(self):
        hist = MagicMock()
        hist.GetName.return_value = "h"
        clone = MagicMock()
        hist.Clone.return_value = clone
        FitFeature.clone_histogram(hist, name_suffix="_copy")
        hist.Clone.assert_called_once_with("h_copy")

    def test_hist_without_get_name(self):
        hist = MagicMock(spec=[])  # no GetName
        hist.Clone = MagicMock(return_value=MagicMock())
        result = FitFeature.clone_histogram(hist)
        hist.Clone.assert_called_once_with("hist_fit_clone")


# ---------------------------------------------------------------------------
# FitFeature._extract_results
# ---------------------------------------------------------------------------

class TestExtractResults(unittest.TestCase):

    def test_none_result_none_func_returns_error(self):
        cached = FitFeature._extract_results(None, None)
        self.assertIn("error", cached)

    def test_func_obj_used_preferentially(self):
        func_obj = MagicMock()
        func_obj.GetNpar.return_value = 3
        func_obj.GetParameter.side_effect = [1.0, 2.0, 3.0]
        func_obj.GetParError.side_effect = [0.1, 0.2, 0.3]
        func_obj.GetChisquare.return_value = 2.5
        func_obj.GetNDF.return_value = 5

        cached = FitFeature._extract_results(None, func_obj)
        self.assertNotIn("error", cached)
        self.assertAlmostEqual(cached["chi2"], 2.5)
        self.assertEqual(cached["ndf"], 5)
        self.assertEqual(len(cached["parameters"]), 3)

    def test_non_zero_status_returns_error(self):
        fit_result = MagicMock()
        fit_result.Get.return_value = None  # no Get method path
        # When func_obj is None and fit_result.Get returns a result with status 1
        result_obj = MagicMock()
        result_obj.Status.return_value = 1
        fit_result.Get.return_value = result_obj

        cached = FitFeature._extract_results(fit_result, None)
        self.assertIn("error", cached)
        self.assertIn("status 1", cached["error"])


# ---------------------------------------------------------------------------
# FitFeature.format_fit_results
# ---------------------------------------------------------------------------

class TestFormatFitResults(unittest.TestCase):

    def _make_cached(self, fit_func="gaus", params=None, errors=None, chi2=1.5, ndf=3, status=0):
        if params is None:
            params = [100.0, 500.0, 5.0] if fit_func.startswith("gaus") else [100.0, 0.0]
        if errors is None:
            errors = [1.0] * len(params)
        return {
            "chi2": chi2,
            "ndf": ndf,
            "status": status,
            "parameters": params,
            "errors": errors,
        }

    def test_error_in_cached_returned_verbatim(self):
        result = FitFeature.format_fit_results("gaus", "SQ", {"error": "Fit exploded"})
        self.assertEqual(result, "Fit exploded")

    def test_gaus_includes_fwhm_centroid_area(self):
        cached = self._make_cached("gaus", params=[100.0, 500.0, 5.0], errors=[1.0, 0.1, 0.05])
        text = FitFeature.format_fit_results("gaus", "SQ", cached)
        self.assertIn("FWHM", text)
        self.assertIn("Centroid", text)
        self.assertIn("Area", text)

    def test_gaus_pol1_includes_fwhm_centroid_area(self):
        cached = self._make_cached("gaus+pol1", params=[100.0, 500.0, 5.0, 0.0, 0.0])
        text = FitFeature.format_fit_results("gaus+pol1", "SQ", cached)
        self.assertIn("FWHM", text)
        self.assertIn("Centroid", text)
        self.assertIn("Area", text)

    def test_2gaus_includes_per_peak_annotations(self):
        params = [100.0, 500.0, 5.0, 80.0, 510.0, 4.5]
        cached = self._make_cached("2gaus", params=params)
        text = FitFeature.format_fit_results("2gaus", "SQ", cached)
        self.assertIn("Peak 1", text)
        self.assertIn("Peak 2", text)

    def test_unknown_func_no_peak_annotations(self):
        cached = self._make_cached("custom_func", params=[1.0, -0.001])
        text = FitFeature.format_fit_results("custom_func", "SQ", cached)
        self.assertNotIn("Peak Annotations", text)

    def test_reduced_chi_square_non_zero_ndf(self):
        cached = {"chi2": 2.5, "ndf": 5, "status": 0, "parameters": [1.0, 0.0], "errors": [0.1, 0.1]}
        text = FitFeature.format_fit_results("gaus+pol1", "SQ", cached)
        self.assertIn("0.5", text)  # 2.5 / 5 = 0.5

    def test_zero_ndf_shows_na(self):
        cached = {"chi2": 2.5, "ndf": 0, "status": 0, "parameters": [1.0, 0.0], "errors": [0.1, 0.1]}
        text = FitFeature.format_fit_results("gaus+pol1", "SQ", cached)
        self.assertIn("N/A", text)

    def test_fit_function_appears_in_output(self):
        cached = self._make_cached("gaus")
        text = FitFeature.format_fit_results("gaus", "SQ", cached)
        self.assertIn("gaus", text)

    def test_fit_option_appears_in_output(self):
        cached = self._make_cached("gaus")
        text = FitFeature.format_fit_results("gaus", "QSRN", cached)
        self.assertIn("QSRN", text)

    def test_unknown_fit_func_uses_generic_param_names(self):
        cached = {
            "chi2": 1.0, "ndf": 2, "status": 0,
            "parameters": [5.0, 6.0],
            "errors": [0.1, 0.1],
        }
        text = FitFeature.format_fit_results("custom_func", "S", cached)
        self.assertIn("p[0]", text)
        self.assertIn("p[1]", text)


# ---------------------------------------------------------------------------
# FitModule (modules/fit_module.py) — domain API tests
# ---------------------------------------------------------------------------

class TestFitModule(unittest.TestCase):
    """Tests for FitModule: the pure-domain module with no tkinter code."""

    def _make_module(self, on_save=None, on_fit_completed=None):
        from modules.fit_module import FitModule
        return FitModule(on_save=on_save, on_fit_completed=on_fit_completed)

    # Construction -----------------------------------------------------------

    def test_default_construction_no_callbacks(self):
        m = self._make_module()
        self.assertIsNone(m._on_save)
        self.assertIsNone(m._on_fit_completed)

    def test_callbacks_stored_at_construction(self):
        on_save = MagicMock()
        on_done = MagicMock()
        m = self._make_module(on_save=on_save, on_fit_completed=on_done)
        self.assertIs(m._on_save, on_save)
        self.assertIs(m._on_fit_completed, on_done)

    def test_backward_compatible_alias(self):
        """FittingFeature must still import and be the same class as FitModule."""
        from modules.fit_module import FittingFeature, FitModule
        self.assertIs(FittingFeature, FitModule)

    # set_histogram ----------------------------------------------------------

    def test_set_histogram_stores_hist(self):
        m = self._make_module()
        hist = MagicMock()
        hist.GetName.return_value = "h"
        hist.Clone.return_value = MagicMock()
        m.set_histogram(hist)
        self.assertIs(m.current_hist, hist)

    def test_set_histogram_creates_clone(self):
        m = self._make_module()
        hist = MagicMock()
        hist.GetName.return_value = "h"
        clone = MagicMock()
        hist.Clone.return_value = clone
        m.set_histogram(hist)
        self.assertIs(m.current_hist_clone, clone)

    def test_set_histogram_none_clears_both(self):
        m = self._make_module()
        m.current_hist = MagicMock()
        m.current_hist_clone = MagicMock()
        m.set_histogram(None)
        self.assertIsNone(m.current_hist)
        self.assertIsNone(m.current_hist_clone)

    # set_peaks --------------------------------------------------------------

    def test_set_peaks_stores_list(self):
        m = self._make_module()
        peaks = [{"energy": 100.0, "counts": 50}, {"energy": 200.0, "counts": 30}]
        m.set_peaks(peaks)
        self.assertEqual(m.detected_peaks, peaks)

    def test_set_peaks_none_stores_empty(self):
        m = self._make_module()
        m.set_peaks(None)
        self.assertEqual(m.detected_peaks, [])

    # estimate_peak_width ----------------------------------------------------

    def test_estimate_peak_width_five_percent(self):
        self.assertAlmostEqual(FitModule_estimate(200.0), 10.0)
        self.assertAlmostEqual(FitModule_estimate(1000.0), 50.0)

    # add_fit / remove_fit ---------------------------------------------------

    def test_add_fit_returns_incremental_id(self):
        m = self._make_module()
        id1 = m.add_fit()
        id2 = m.add_fit()
        self.assertEqual(id2, id1 + 1)

    def test_add_fit_stores_domain_state(self):
        m = self._make_module()
        fit_id = m.add_fit(energy=300.0, width=15.0, peak_idx=2)
        state = m.get_fit_state(fit_id)
        self.assertIsNotNone(state)
        self.assertAlmostEqual(state["energy"], 300.0)
        self.assertAlmostEqual(state["width"], 15.0)
        self.assertEqual(state["peak_idx"], 2)
        self.assertEqual(state["fit_func"], "gaus")

    def test_add_fit_no_tkinter_objects_in_state(self):
        """fit_state must contain only plain Python types (no tkinter Vars)."""
        import tkinter
        m = self._make_module()
        fit_id = m.add_fit(energy=100.0, width=10.0)
        state = m.get_fit_state(fit_id)
        for key, value in state.items():
            # None, str, int, float, bool, list, dict are all OK
            self.assertNotIsInstance(
                value,
                tkinter.Variable,
                msg=f"fit_state['{key}'] is a tkinter Variable — must be a plain Python type",
            )

    def test_remove_fit_deletes_state(self):
        m = self._make_module()
        fit_id = m.add_fit()
        m.remove_fit(fit_id)
        self.assertIsNone(m.get_fit_state(fit_id))

    def test_list_fits_empty(self):
        m = self._make_module()
        self.assertEqual(m.list_fits(), [])

    def test_list_fits_returns_id_name_pairs(self):
        m = self._make_module()
        fid1 = m.add_fit()
        fid2 = m.add_fit(energy=500.0)
        fits = m.list_fits()
        self.assertEqual(len(fits), 2)
        ids = [f[0] for f in fits]
        self.assertIn(fid1, ids)
        self.assertIn(fid2, ids)

    def test_get_fit_display_name_with_energy(self):
        m = self._make_module()
        fit_id = m.add_fit(energy=511.0)
        name = m.get_fit_display_name(fit_id)
        self.assertIn("511", name)

    def test_get_fit_display_name_without_energy(self):
        m = self._make_module()
        fit_id = m.add_fit()
        name = m.get_fit_display_name(fit_id)
        self.assertIn(str(fit_id), name)

    # update_fit_params -------------------------------------------------------

    def test_update_fit_params_sets_domain_state(self):
        m = self._make_module()
        fit_id = m.add_fit()
        m.update_fit_params(
            fit_id,
            fit_func="landau",
            energy=250.0,
            width=20.0,
            params=[1.0, 2.0, 3.0],
            fixed_params=[False, True, False],
            fit_options="SQ",
        )
        state = m.get_fit_state(fit_id)
        self.assertEqual(state["fit_func"], "landau")
        self.assertAlmostEqual(state["energy"], 250.0)
        self.assertEqual(state["params"], [1.0, 2.0, 3.0])
        self.assertEqual(state["fixed_params"], [False, True, False])

    def test_update_fit_params_unknown_id_does_not_raise(self):
        m = self._make_module()
        m.update_fit_params(
            999,
            fit_func="gaus",
            energy=None,
            width=None,
            params=[],
            fixed_params=[],
            fit_options="SQ",
        )

    # invoke_save -------------------------------------------------------------

    def test_invoke_save_calls_callback_with_fit_state(self):
        on_save = MagicMock()
        m = self._make_module(on_save=on_save)
        fit_id = m.add_fit(energy=100.0)
        m.invoke_save(fit_id)
        on_save.assert_called_once()
        called_state = on_save.call_args[0][0]
        self.assertEqual(called_state["fit_id"], fit_id)

    def test_invoke_save_no_callback_does_not_raise(self):
        m = self._make_module()
        fit_id = m.add_fit()
        m.invoke_save(fit_id)  # no on_save — must not raise

    def test_invoke_save_unknown_id_does_not_raise(self):
        on_save = MagicMock()
        m = self._make_module(on_save=on_save)
        m.invoke_save(9999)
        on_save.assert_not_called()

    # perform_fit (mocked ROOT) -----------------------------------------------

    def test_perform_fit_without_histogram_returns_error(self):
        m = self._make_module()
        fit_id = m.add_fit(energy=100.0, width=10.0)
        result = m.perform_fit(fit_id, MagicMock())
        self.assertIn("error", result)

    def test_perform_fit_unknown_id_returns_error(self):
        m = self._make_module()
        result = m.perform_fit(999, MagicMock())
        self.assertIn("error", result)

    def test_perform_fit_fires_on_fit_completed(self):
        """on_fit_completed must be called even when the ROOT fit mock succeeds."""
        on_done = MagicMock()
        m = self._make_module(on_fit_completed=on_done)

        hist = MagicMock()
        hist.GetName.return_value = "h"
        clone = MagicMock()
        hist.Clone.return_value = clone
        clone.GetXaxis.return_value = None  # forces default range
        clone.GetListOfFunctions.return_value = None
        m.set_histogram(hist)

        fit_id = m.add_fit(energy=100.0, width=10.0)

        # Build a mock ROOT that makes FitFeature.perform_fit succeed.
        root = MagicMock()
        tf1_mock = MagicMock()
        tf1_mock.GetNpar.return_value = 3
        tf1_mock.GetParameter.return_value = 1.0
        tf1_mock.GetParError.return_value = 0.01
        tf1_mock.GetChisquare.return_value = 1.5
        tf1_mock.GetNDF.return_value = 2
        root.TF1.return_value = tf1_mock
        root.gROOT.IsBatch.return_value = False
        clone.Fit.return_value = MagicMock()

        m.perform_fit(fit_id, root)
        on_done.assert_called_once()
        called_fit_id, called_cached = on_done.call_args[0]
        self.assertEqual(called_fit_id, fit_id)


def FitModule_estimate(energy: float) -> float:
    """Helper to call FitModule.estimate_peak_width without creating an instance."""
    from modules.fit_module import FitModule
    return FitModule.estimate_peak_width(energy)


if __name__ == "__main__":
    unittest.main()

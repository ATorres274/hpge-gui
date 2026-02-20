"""Unit tests for features.fit_feature.FitFeature and modules.fit_module.FittingFeature.

These tests cover the refactored pure-computation feature and the callback
wiring added to FittingFeature.  No ROOT or tkinter installation is required.
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

    def test_landau_returns_three_labels(self):
        labels = FitFeature.get_param_labels("landau")
        self.assertEqual(len(labels), 3)
        self.assertIn("Width", labels[2])

    def test_expo_returns_two_labels(self):
        labels = FitFeature.get_param_labels("expo")
        self.assertEqual(len(labels), 2)

    def test_pol3_returns_four_labels(self):
        labels = FitFeature.get_param_labels("pol3")
        self.assertEqual(len(labels), 4)

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

    def test_pol2_display_names(self):
        names = FitFeature.get_param_display_names("pol2")
        self.assertEqual(names, ["a0", "a1", "a2"])

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

    def test_landau_returns_three_params(self):
        params = FitFeature.default_fit_params("landau", self._make_hist(), 100.0, 10.0, 90.0, 110.0)
        self.assertEqual(len(params), 3)

    def test_expo_returns_two_params(self):
        params = FitFeature.default_fit_params("expo", self._make_hist(), None, None, 0.0, 1000.0)
        self.assertEqual(len(params), 2)
        self.assertAlmostEqual(params[0], 0.0)

    def test_pol1_returns_two_params(self):
        params = FitFeature.default_fit_params("pol1", self._make_hist(), None, None, 0.0, 500.0)
        self.assertEqual(len(params), 2)

    def test_pol2_returns_three_params(self):
        params = FitFeature.default_fit_params("pol2", self._make_hist(), None, None, 0.0, 500.0)
        self.assertEqual(len(params), 3)

    def test_pol3_returns_four_params(self):
        params = FitFeature.default_fit_params("pol3", self._make_hist(), None, None, 0.0, 500.0)
        self.assertEqual(len(params), 4)

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
            params = [100.0, 500.0, 5.0] if fit_func == "gaus" else [100.0, 0.0]
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

    def test_landau_includes_most_probable_value(self):
        cached = self._make_cached("landau", params=[100.0, 300.0, 15.0])
        text = FitFeature.format_fit_results("landau", "SQ", cached)
        self.assertIn("Most Probable Value", text)
        self.assertIn("Width", text)

    def test_expo_no_peak_annotations(self):
        cached = self._make_cached("expo", params=[1.0, -0.001])
        text = FitFeature.format_fit_results("expo", "SQ", cached)
        self.assertNotIn("Peak Annotations", text)

    def test_reduced_chi_square_non_zero_ndf(self):
        cached = self._make_cached(chi2=2.5, ndf=5, params=[1.0, 0.0])
        text = FitFeature.format_fit_results("pol1", "SQ", cached)
        self.assertIn("0.5", text)  # 2.5 / 5 = 0.5

    def test_zero_ndf_shows_na(self):
        cached = self._make_cached(chi2=2.5, ndf=0, params=[1.0, 0.0])
        text = FitFeature.format_fit_results("pol1", "SQ", cached)
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
# FittingFeature (fit_module) callback wiring
# ---------------------------------------------------------------------------

class TestFittingFeatureCallbacks(unittest.TestCase):

    def test_default_construction_no_callbacks(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        self.assertIsNone(feature._on_save)
        self.assertIsNone(feature._on_preview_render)

    def test_callbacks_stored_at_construction(self):
        from modules.fit_module import FittingFeature
        on_save = MagicMock()
        on_preview = MagicMock()
        feature = FittingFeature(on_save=on_save, on_preview_render=on_preview)
        self.assertIs(feature._on_save, on_save)
        self.assertIs(feature._on_preview_render, on_preview)

    def test_invoke_save_calls_callback(self):
        from modules.fit_module import FittingFeature
        on_save = MagicMock()
        feature = FittingFeature(on_save=on_save)
        fit_state = {"cached_results": {"status": 0}}
        feature._invoke_save(fit_state)
        on_save.assert_called_once_with(fit_state)

    def test_invoke_save_no_callback_does_not_raise(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        # Should not raise even when _on_save is None
        feature._invoke_save({"cached_results": None})

    def test_on_selection_stores_histogram(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        hist = MagicMock()
        hist.GetName.return_value = "test_h"
        clone = MagicMock()
        hist.Clone.return_value = clone
        feature.on_selection(None, hist, "/path/to/hist")
        self.assertIs(feature.current_hist, hist)

    def test_on_selection_clones_histogram(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        hist = MagicMock()
        hist.GetName.return_value = "h"
        clone = MagicMock()
        hist.Clone.return_value = clone
        feature.on_selection(None, hist, "/path")
        self.assertIs(feature.current_hist_clone, clone)

    def test_on_selection_none_clears_clone(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        feature.current_hist_clone = MagicMock()
        feature.on_selection(None, None, "")
        self.assertIsNone(feature.current_hist_clone)

    def test_get_fit_range_for_tab_delegates_to_fit_feature(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        energy_var = MagicMock()
        energy_var.get.return_value = "100.0"
        width_var = MagicMock()
        width_var.get.return_value = "20.0"
        fit_state = {"energy_var": energy_var, "width_var": width_var}
        xmin, xmax = feature._get_fit_range_for_tab(fit_state)
        self.assertAlmostEqual(xmin, 90.0)
        self.assertAlmostEqual(xmax, 110.0)

    def test_get_fit_range_empty_vars_returns_none(self):
        from modules.fit_module import FittingFeature
        feature = FittingFeature()
        energy_var = MagicMock()
        energy_var.get.return_value = ""
        width_var = MagicMock()
        width_var.get.return_value = ""
        fit_state = {"energy_var": energy_var, "width_var": width_var}
        result = feature._get_fit_range_for_tab(fit_state)
        self.assertEqual(result, (None, None))


if __name__ == "__main__":
    unittest.main()

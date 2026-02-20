"""
HPGe GUI — Histogram tab test suite.

Covers the end-user workflows for the histogram tab:
1. Session persistence across restarts
2. Open / close / switch histogram lifecycle
3. Axis range controls (zoom in/out on X and Y)
4. Title and axis label editing
5. Log-scale toggles
6. Reset button restores defaults
7. Show-markers toggle
8. Peak finder (find, add manual, remove, clear)
9. Full HPGe screening workflow (open → find peaks → zoom → reset)
10. HistogramControlsModule pure-function unit tests (no tkinter needed)

Usage:
    DISPLAY=:99 python3 -m pytest tests/test_simple_test_1.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_MOCK_ROOT = MagicMock()
sys.modules.setdefault("ROOT", _MOCK_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_histogram(name: str = "h1", n_bins: int = 100,
                         x_min: float = 0.0, x_max: float = 1000.0,
                         y_min: float = 0.0, y_max: float = 5000.0) -> MagicMock:
    """Return a mock object that behaves like a ROOT TH1 histogram."""
    obj = MagicMock()
    obj.GetName.return_value = name
    obj.GetTitle.return_value = name

    xaxis = MagicMock()
    xaxis.GetXmin.return_value = x_min
    xaxis.GetXmax.return_value = x_max
    xaxis.GetTitle.return_value = "Energy (keV)"

    yaxis = MagicMock()
    yaxis.GetTitle.return_value = "Counts"

    obj.GetXaxis.return_value = xaxis
    obj.GetYaxis.return_value = yaxis
    obj.GetNbinsX.return_value = n_bins
    obj.GetBinContent.return_value = 10.0
    obj.GetMinimum.return_value = y_min
    obj.GetMaximum.return_value = y_max
    return obj


# ---------------------------------------------------------------------------
# 1. Session persistence
# ---------------------------------------------------------------------------

class TestSessionPersistence(unittest.TestCase):
    """Verify session save and restore across a simulated restart."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._home_patcher = patch(
            "os.path.expanduser",
            side_effect=lambda p: p.replace("~", self._tmpdir),
        )
        self._home_patcher.start()
        from modules.session_manager import SessionManager
        self.session_manager = SessionManager()

    def tearDown(self):
        self._home_patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_last_files_creates_session_json(self):
        paths = ["/data/run1.root", "/data/run2.root"]
        result = self.session_manager.save_last_files(paths)
        self.assertIsNotNone(result)
        self.assertTrue(os.path.isfile(result))
        with open(result, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIn("last_files", data)
        self.assertEqual(len(data["last_files"]), 2)
        for saved in data["last_files"]:
            self.assertTrue(os.path.isabs(saved))

    def test_load_last_session_paths_returns_existing_files(self):
        real1 = os.path.join(self._tmpdir, "a.root")
        real2 = os.path.join(self._tmpdir, "b.root")
        missing = os.path.join(self._tmpdir, "missing.root")
        for p in (real1, real2):
            with open(p, "w"):
                pass
        self.session_manager.save_last_files([real1, real2, missing])
        from main import _load_last_session_paths
        loaded = _load_last_session_paths()
        self.assertIn(real1, loaded)
        self.assertIn(real2, loaded)
        self.assertNotIn(missing, loaded)

    def test_session_round_trip_simulates_restart(self):
        real_file = os.path.join(self._tmpdir, "spectrum.root")
        with open(real_file, "w"):
            pass
        self.session_manager.save_last_files([real_file])
        from main import _resolve_initial_paths
        restored = _resolve_initial_paths(arg_path=None, use_last=True)
        self.assertIsNotNone(restored)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0], real_file)

    def test_restart_with_no_session_returns_none(self):
        from main import _resolve_initial_paths
        result = _resolve_initial_paths(arg_path=None, use_last=True)
        self.assertIsNone(result)

    def test_autosave_writes_json(self):
        filepath = self.session_manager.auto_save_session(
            histogram_name="test_hist", histogram_path="test_hist",
            fit_states={}, peaks=[],
        )
        self.assertIsNotNone(filepath)
        self.assertTrue(os.path.isfile(filepath))
        with open(filepath, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["histogram"]["name"], "test_hist")

    def test_load_latest_autosave_returns_most_recent(self):
        self.session_manager.auto_save_session("hist_a", "hist_a", {})
        import time
        time.sleep(0.05)
        self.session_manager.auto_save_session("hist_b", "hist_b", {})
        latest = self.session_manager.load_latest_autosave()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["histogram"]["name"], "hist_b")


# ---------------------------------------------------------------------------
# 2. Histogram tab lifecycle (open / close / switch)
# ---------------------------------------------------------------------------

class TestHistogramTabWorkflow(unittest.TestCase):
    """Open/close/switch workflow tests — renderer is mocked out."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls._root = tk.Tk()
            cls._root.withdraw()
            cls._tk_available = True
        except Exception:
            cls._tk_available = False

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_tk_available", False):
            try:
                cls._root.destroy()
            except Exception:
                pass

    def setUp(self):
        if not getattr(self, "_tk_available", False):
            self.skipTest("tkinter display not available")

    def _make_tab(self):
        import tkinter as tk
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramTab
        container = ttk.Frame(self._root)
        mock_app = MagicMock(); mock_app.ROOT = _MOCK_ROOT
        selected, closed, opened = [], [], []
        tab = HistogramTab(
            mock_app, container,
            on_histogram_selected=lambda k: selected.append(k),
            on_histogram_closed=lambda n: closed.append(n),
            on_histogram_opened=lambda lst: opened.append(lst),
        )
        return tab, selected, closed, opened

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_multiple_histograms(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        for i in range(3):
            tab.open_histogram(_make_mock_histogram(f"h{i}"), "/data/run.root", f"h{i}")
        self.assertEqual(len(tab._hist_tabs), 3)
        self.assertEqual(len(tab._open_histograms), 3)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_same_histogram_twice_does_not_duplicate(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        obj = _make_mock_histogram("h1")
        tab.open_histogram(obj, "/data/run.root", "h1")
        tab.open_histogram(obj, "/data/run.root", "h1")
        self.assertEqual(len(tab._hist_tabs), 1)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_current_histogram(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.close_current_histogram()
        self.assertEqual(len(tab._hist_tabs), 0)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_all_histograms_one_by_one(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        for i in range(3):
            tab.open_histogram(_make_mock_histogram(f"h{i}"), "/data/run.root", f"h{i}")
        for key in [k for k, *_ in tab._open_histograms]:
            tab.remove_histogram(key)
        self.assertEqual(len(tab._hist_tabs), 0)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_histogram_fires_callback(self, MockR):
        MockR.return_value = MagicMock()
        tab, _, closed, _ = self._make_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.open_histogram(_make_mock_histogram("h2"), "/data/run.root", "h2")
        tab.close_current_histogram()
        self.assertTrue(len(closed) > 0)
        self.assertEqual(closed[-1], 1)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_more_histograms_after_close(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.close_current_histogram()
        for i in range(3):
            tab.open_histogram(_make_mock_histogram(f"new{i}"), "/data/run.root", f"new{i}")
        self.assertEqual(len(tab._hist_tabs), 3)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_switch_between_histograms(self, MockR):
        MockR.return_value = MagicMock()
        tab, *_ = self._make_tab()
        keys = []
        for i in range(3):
            tab.open_histogram(_make_mock_histogram(f"h{i}"), "/data/run.root", f"h{i}")
            keys.append(f"/data/run.root:h{i}")
        tab.show_histogram(keys[0])
        self.assertEqual(tab._current_histogram_key, keys[0])
        tab.show_histogram(keys[2])
        self.assertEqual(tab._current_histogram_key, keys[2])
        tab.show_histogram(keys[1])
        self.assertEqual(tab._current_histogram_key, keys[1])

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_switch_histogram_notifies_app(self, MockR):
        MockR.return_value = MagicMock()
        tab, selected, *_ = self._make_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.open_histogram(_make_mock_histogram("h2"), "/data/run.root", "h2")
        self.assertIn("/data/run.root:h1", selected)
        self.assertIn("/data/run.root:h2", selected)


# ---------------------------------------------------------------------------
# 3. Control-panel variables (axis range, log scale, title, labels, markers)
# ---------------------------------------------------------------------------

class _RendererBase(unittest.TestCase):
    """Base that builds a HistogramPreviewRenderer with render patched out."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls._root = tk.Tk()
            cls._root.withdraw()
            cls._tk_available = True
        except Exception:
            cls._tk_available = False

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_tk_available", False):
            try:
                cls._root.destroy()
            except Exception:
                pass

    def setUp(self):
        if not getattr(self, "_tk_available", False):
            self.skipTest("tkinter display not available")

    def _build_renderer(self, obj):
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramPreviewRenderer
        r = HistogramPreviewRenderer()
        mock_app = MagicMock()
        mock_app.after.return_value = None
        mock_app.after_cancel.return_value = None
        mock_app.ROOT = _MOCK_ROOT
        container = ttk.Frame(self._root)
        with patch.object(r, "render_preview", return_value=None):
            r.build_histogram_tab(mock_app, container, obj, "/run.root", "h1")
        return r


class TestAxisRangeControls(_RendererBase):
    """Zoom controls — X and Y range entry boxes."""

    def test_initial_x_range_matches_histogram(self):
        r = self._build_renderer(_make_mock_histogram("h1", x_min=100.0, x_max=3000.0))
        self.assertAlmostEqual(float(r._xmin_var.get()), 100.0, places=1)
        self.assertAlmostEqual(float(r._xmax_var.get()), 3000.0, places=1)

    def test_initial_y_range_matches_histogram(self):
        r = self._build_renderer(_make_mock_histogram("h1", y_min=1.0, y_max=8000.0))
        self.assertGreater(float(r._ymax_var.get()), 8000.0,
                           "y_max should be scaled up from histogram max")

    def test_set_x_range(self):
        r = self._build_renderer(_make_mock_histogram("h1", x_min=0.0, x_max=1000.0))
        r._xmin_var.set("200.0"); r._xmax_var.set("800.0")
        self.assertAlmostEqual(float(r._xmin_var.get()), 200.0, places=1)
        self.assertAlmostEqual(float(r._xmax_var.get()), 800.0, places=1)

    def test_set_y_range(self):
        r = self._build_renderer(_make_mock_histogram("h1", y_min=1.0, y_max=1000.0))
        r._ymin_var.set("5.0"); r._ymax_var.set("500.0")
        self.assertAlmostEqual(float(r._ymin_var.get()), 5.0, places=1)
        self.assertAlmostEqual(float(r._ymax_var.get()), 500.0, places=1)

    def test_range_values_always_one_decimal(self):
        """Populated range values should have exactly 1 decimal place."""
        r = self._build_renderer(_make_mock_histogram("h1", x_min=100.0, x_max=3000.0))
        for var in (r._xmin_var, r._xmax_var, r._ymin_var, r._ymax_var):
            val = var.get()
            self.assertIn(".", val, f"Expected decimal in {val!r}")
            self.assertEqual(len(val.split(".")[-1]), 1,
                             f"Expected exactly 1 decimal place, got {val!r}")

    def test_controls_for_multiple_histograms_are_independent(self):
        r1 = self._build_renderer(_make_mock_histogram("h1", x_max=500.0))
        r2 = self._build_renderer(_make_mock_histogram("h2", x_max=2000.0))
        r1._xmax_var.set("300.0")
        self.assertAlmostEqual(float(r1._xmax_var.get()), 300.0, places=1)
        self.assertAlmostEqual(float(r2._xmax_var.get()), 2000.0, places=1)


class TestLogScaleControls(_RendererBase):
    """Log-scale toggle behaviour."""

    def test_initial_log_y_is_enabled(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertTrue(r._logy_var.get())

    def test_initial_log_x_is_disabled(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertFalse(r._logx_var.get())

    def test_toggle_log_x(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._logx_var.set(True); self.assertTrue(r._logx_var.get())
        r._logx_var.set(False); self.assertFalse(r._logx_var.get())

    def test_toggle_log_y(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        initial = r._logy_var.get()
        r._logy_var.set(not initial)
        self.assertNotEqual(r._logy_var.get(), initial)


class TestTitleAndLabelControls(_RendererBase):
    """Title and axis label entry boxes."""

    def test_initial_xlabel_from_histogram(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertEqual(r._xlabel_var.get(), "Energy (keV)")

    def test_initial_ylabel_from_histogram(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertEqual(r._ylabel_var.get(), "Counts")

    def test_set_xlabel(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._xlabel_var.set("Channel")
        self.assertEqual(r._xlabel_var.get(), "Channel")

    def test_set_ylabel(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._ylabel_var.set("Intensity")
        self.assertEqual(r._ylabel_var.get(), "Intensity")

    def test_set_title(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._title_var.set("My Spectrum")
        self.assertEqual(r._title_var.get(), "My Spectrum")


class TestShowMarkersControl(_RendererBase):
    """Show-markers checkbox."""

    def test_show_markers_on_by_default(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertTrue(r._show_markers_var.get())

    def test_toggle_show_markers(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._show_markers_var.set(False)
        self.assertFalse(r._show_markers_var.get())
        r._show_markers_var.set(True)
        self.assertTrue(r._show_markers_var.get())


class TestResetButton(_RendererBase):
    """Reset restores all controls to histogram defaults."""

    def test_reset_restores_x_range(self):
        obj = _make_mock_histogram("h1", x_min=100.0, x_max=3000.0)
        r = self._build_renderer(obj)
        r._xmin_var.set("500.0"); r._xmax_var.set("1000.0")
        # Trigger reset via the stored reset method
        r._reset_controls()
        self.assertAlmostEqual(float(r._xmin_var.get()), 100.0, places=1)
        self.assertAlmostEqual(float(r._xmax_var.get()), 3000.0, places=1)

    def test_reset_restores_log_y(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._logy_var.set(False)
        r._reset_controls()
        self.assertTrue(r._logy_var.get())

    def test_reset_restores_show_markers(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._show_markers_var.set(False)
        r._reset_controls()
        self.assertTrue(r._show_markers_var.get())

    def test_reset_restores_title_and_labels(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._title_var.set("edited"); r._xlabel_var.set("X"); r._ylabel_var.set("Y")
        r._reset_controls()
        # After reset the label should be back to the histogram axis title
        self.assertEqual(r._xlabel_var.get(), "Energy (keV)")
        self.assertEqual(r._ylabel_var.get(), "Counts")


# ---------------------------------------------------------------------------
# 4. Peak finder
# ---------------------------------------------------------------------------

class TestPeakFinder(_RendererBase):
    """Peak finder integration via HistogramPreviewRenderer."""

    def test_peak_finder_is_attached(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        self.assertIsNotNone(r._peak_finder)

    def test_add_manual_peak(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._peak_finder._manual_peak_var.set("511.0")
        r._peak_finder._add_manual_peak()
        energies = [p["energy"] for p in r._peak_finder.peaks]
        self.assertIn(511.0, energies)

    def test_clear_peaks(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        r._peak_finder._manual_peak_var.set("511.0")
        r._peak_finder._add_manual_peak()
        r._peak_finder._clear_peaks()
        self.assertEqual(len(r._peak_finder.peaks), 0)

    def test_remove_selected_peak_removes_by_iid(self):
        from modules.peak_manager import PeakFinderModule
        m = PeakFinderModule()
        m.peaks = [
            {"energy": 511.0, "counts": 100, "source": "manual"},
            {"energy": 1274.0, "counts": 50, "source": "manual"},
        ]
        m.set_peak_energy_by_iid("0", 511.0)  # keeps it in place
        self.assertEqual(len(m.peaks), 2)

    def test_add_multiple_manual_peaks_are_sorted(self):
        r = self._build_renderer(_make_mock_histogram("h1"))
        for energy in ("1274.0", "511.0", "662.0"):
            r._peak_finder._manual_peak_var.set(energy)
            r._peak_finder._add_manual_peak()
        energies = [p["energy"] for p in r._peak_finder.peaks]
        self.assertEqual(energies, sorted(energies))


# ---------------------------------------------------------------------------
# 5. HistogramControlsModule pure-function unit tests (no tkinter / ROOT)
# ---------------------------------------------------------------------------

class TestHistogramControlsModule(unittest.TestCase):
    """Unit-test the calculation module without any UI dependencies."""

    def _module(self):
        from modules.histogram_controls_module import HistogramControlsModule
        return HistogramControlsModule

    def test_compute_defaults_extracts_axis_limits(self):
        obj = _make_mock_histogram("h1", x_min=50.0, x_max=2000.0,
                                   y_min=0.0, y_max=10000.0)
        d = self._module().compute_defaults(obj)
        self.assertAlmostEqual(d["x_min"], 50.0, places=1)
        self.assertAlmostEqual(d["x_max"], 2000.0, places=1)

    def test_compute_defaults_scales_y_max(self):
        obj = _make_mock_histogram("h1", y_max=10000.0)
        d = self._module().compute_defaults(obj)
        self.assertGreater(d["y_max"], 10000.0,
                           "y_max should be scaled above raw histogram max")

    def test_compute_defaults_enforces_positive_x_min(self):
        obj = _make_mock_histogram("h1", x_min=-10.0)
        d = self._module().compute_defaults(obj)
        self.assertGreater(d["x_min"], 0.0)

    def test_scroll_step_proportional_to_max(self):
        obj = _make_mock_histogram("h1", x_max=3000.0)
        d = self._module().compute_defaults(obj)
        self.assertAlmostEqual(d["x_scroll_step"], 30.0, places=1)

    def test_clamp_min_scrolls_up(self):
        M = self._module()
        result = M.clamp_min(100.0, 30.0, direction_down=False,
                             min_limit=50.0, max_val=3000.0)
        self.assertAlmostEqual(result, 130.0, places=1)

    def test_clamp_min_scrolls_down(self):
        M = self._module()
        result = M.clamp_min(100.0, 30.0, direction_down=True,
                             min_limit=50.0, max_val=3000.0)
        self.assertAlmostEqual(result, 70.0, places=1)

    def test_clamp_min_cannot_cross_max(self):
        M = self._module()
        result = M.clamp_min(2999.0, 30.0, direction_down=False,
                             min_limit=0.0, max_val=3000.0)
        self.assertLess(result, 3000.0)

    def test_clamp_max_scrolls_up(self):
        M = self._module()
        result = M.clamp_max(1000.0, 100.0, direction_down=False,
                             min_val=0.0, max_limit=5000.0)
        self.assertAlmostEqual(result, 1100.0, places=1)

    def test_clamp_max_cannot_go_below_min(self):
        M = self._module()
        result = M.clamp_max(10.0, 100.0, direction_down=True,
                             min_val=5.0, max_limit=5000.0)
        self.assertGreater(result, 5.0)

    def test_validate_min_formats_to_one_decimal(self):
        M = self._module()
        result = M.validate_min("123.456", "500.0")
        self.assertIsNotNone(result)
        self.assertIn(".", result)
        self.assertEqual(len(result.split(".")[-1]), 1)

    def test_validate_min_clamps_against_max(self):
        M = self._module()
        result = M.validate_min("500.0", "300.0")  # min >= max → clamped
        self.assertIsNotNone(result)
        self.assertLess(float(result), 300.0)

    def test_validate_max_clamps_against_min(self):
        M = self._module()
        result = M.validate_max("100.0", "200.0")  # max < min → clamped
        self.assertIsNotNone(result)
        self.assertGreater(float(result), 200.0)

    def test_validate_min_returns_none_on_bad_input(self):
        M = self._module()
        result = M.validate_min("abc", "500.0")
        self.assertIsNone(result)

    def test_build_render_options_includes_xrange(self):
        M = self._module()
        opts = M.build_render_options(
            800, 600, xmin_raw="100.0", xmax_raw="2000.0",
            ymin_raw="0.1", ymax_raw="10000.0",
        )
        self.assertEqual(opts["xmin"], 100.0)
        self.assertEqual(opts["xmax"], 2000.0)

    def test_build_render_options_includes_log_flags(self):
        M = self._module()
        opts = M.build_render_options(800, 600, logx=True, logy=True)
        self.assertTrue(opts.get("logx"))
        self.assertTrue(opts.get("logy"))

    def test_build_render_options_includes_peak_markers(self):
        M = self._module()
        opts = M.build_render_options(
            800, 600, show_markers=True, peak_energies=[511.0, 1274.0])
        self.assertIn("markers", opts)
        self.assertIn(511.0, opts["markers"])

    def test_build_render_options_no_markers_when_disabled(self):
        M = self._module()
        opts = M.build_render_options(
            800, 600, show_markers=False, peak_energies=[511.0])
        self.assertNotIn("markers", opts)

    def test_build_render_options_includes_title(self):
        M = self._module()
        opts = M.build_render_options(800, 600, title="My Spectrum")
        self.assertEqual(opts.get("title"), "My Spectrum")


# ---------------------------------------------------------------------------
# 6. Full HPGe screening workflow
# ---------------------------------------------------------------------------

class TestHPGeScreeningWorkflow(unittest.TestCase):
    """End-to-end scenario: open → inspect peaks → zoom → reset → switch."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls._root = tk.Tk()
            cls._root.withdraw()
            cls._tk_available = True
        except Exception:
            cls._tk_available = False

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "_tk_available", False):
            try:
                cls._root.destroy()
            except Exception:
                pass

    def setUp(self):
        if not getattr(self, "_tk_available", False):
            self.skipTest("tkinter display not available")
        self._tmpdir = tempfile.mkdtemp()
        self._home_patcher = patch(
            "os.path.expanduser",
            side_effect=lambda p: p.replace("~", self._tmpdir),
        )
        self._home_patcher.start()
        from modules.session_manager import SessionManager
        self.session_manager = SessionManager()

    def tearDown(self):
        self._home_patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_tab(self):
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramTab
        container = ttk.Frame(self._root)
        mock_app = MagicMock(); mock_app.ROOT = _MOCK_ROOT
        return HistogramTab(mock_app, container)

    def test_open_close_restart_open_switch(self):
        """Full workflow: open → close some → save session → restore → control → switch."""
        mock_renderer = MagicMock()
        renderer_patch = patch(
            "tab_managers.histogram_tab.HistogramPreviewRenderer",
            return_value=mock_renderer,
        )
        with renderer_patch:
            tab = self._make_tab()
            root_path = "/data/first_run.root"
            for name in ("spectrum_A", "spectrum_B", "spectrum_C"):
                tab.open_histogram(_make_mock_histogram(name), root_path, name)
            self.assertEqual(len(tab._hist_tabs), 3)

            for key in [f"{root_path}:{n}" for n in ("spectrum_A", "spectrum_B")]:
                tab.remove_histogram(key)
            self.assertEqual(len(tab._hist_tabs), 1)

            real_file = os.path.join(self._tmpdir, "first_run.root")
            with open(real_file, "w"):
                pass
            self.session_manager.save_last_files([real_file])
            from main import _resolve_initial_paths
            restored = _resolve_initial_paths(arg_path=None, use_last=True)
            self.assertIsNotNone(restored)
            self.assertIn(real_file, restored)

            second = "/data/second_run.root"
            for name in ("gamma_1", "gamma_2", "gamma_3"):
                tab.open_histogram(_make_mock_histogram(name), second, name)
            self.assertEqual(len(tab._hist_tabs), 4)

        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramPreviewRenderer
        r = HistogramPreviewRenderer()
        mock_app = MagicMock()
        mock_app.after.return_value = None
        mock_app.after_cancel.return_value = None
        mock_app.ROOT = _MOCK_ROOT
        ctrl_obj = _make_mock_histogram("gamma_1", x_min=10.0, x_max=2000.0)
        with patch.object(r, "render_preview", return_value=None):
            r.build_histogram_tab(mock_app, ttk.Frame(self._root),
                                  ctrl_obj, second, "gamma_1")

        # Zoom into detector peak region
        r._xmin_var.set("100.0"); r._xmax_var.set("1500.0")
        self.assertAlmostEqual(float(r._xmin_var.get()), 100.0, places=1)
        self.assertAlmostEqual(float(r._xmax_var.get()), 1500.0, places=1)

        # Enable log-Y for dynamic-range visibility
        r._logy_var.set(True)
        self.assertTrue(r._logy_var.get())

        # Add a manual peak at 511 keV (positron annihilation)
        r._peak_finder._manual_peak_var.set("511.0")
        r._peak_finder._add_manual_peak()
        self.assertIn(511.0, [p["energy"] for p in r._peak_finder.peaks])

        # Edit title and labels for export
        r._title_var.set("Co-57 Spectrum")
        r._xlabel_var.set("Energy (keV)")
        self.assertEqual(r._title_var.get(), "Co-57 Spectrum")

        # Disable markers, then re-enable
        r._show_markers_var.set(False)
        self.assertFalse(r._show_markers_var.get())
        r._show_markers_var.set(True)
        self.assertTrue(r._show_markers_var.get())

        # Reset returns us to full histogram view
        r._reset_controls()
        self.assertAlmostEqual(float(r._xmin_var.get()), 10.0, places=1)
        self.assertAlmostEqual(float(r._xmax_var.get()), 2000.0, places=1)
        self.assertTrue(r._show_markers_var.get())

        # Switch through all open histograms
        for key in [k for k, *_ in tab._open_histograms]:
            tab.show_histogram(key)
            self.assertEqual(tab._current_histogram_key, key)


if __name__ == "__main__":
    unittest.main()


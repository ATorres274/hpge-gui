"""
Simple Test 1: Test scripts for the HPGe GUI histogram workflow.

Covers the following scenarios:
1. Opening multiple histograms
2. Closing histograms
3. Client restart with session persistence (save/restore)
4. Opening more histograms after a session restore
5. Playing with histogram controls (axis ranges and log-scale toggles)
6. Switching between open histograms

These tests mock PyROOT (which may not be installed) and use a headless
tkinter session so they can run in CI without a physical display.

Usage:
    DISPLAY=:99 python -m pytest tests/test_simple_test_1.py -v
    # or via unittest:
    DISPLAY=:99 python -m unittest tests.test_simple_test_1 -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Ensure the project root is on the Python path so modules can be imported.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Stub out PyROOT before any project modules are imported.  This lets the
# test suite run on machines where ROOT is not installed.
# ---------------------------------------------------------------------------
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
# 1. Tests for SessionManager (session persistence / restart flow)
# ---------------------------------------------------------------------------

class TestSessionPersistence(unittest.TestCase):
    """Tests that verify session save and restore across a simulated restart."""

    def setUp(self):
        """Create a temporary directory to isolate session files."""
        self._tmpdir = tempfile.mkdtemp()
        # Patch the home directory used by SessionManager so nothing is
        # written to the real user's home during tests.
        self._home_patcher = patch("os.path.expanduser",
                                   side_effect=lambda p: p.replace("~", self._tmpdir))
        self._home_patcher.start()

        # Import after patching so the session directory is created in tmpdir.
        from modules.session_manager import SessionManager
        self.session_manager = SessionManager()

    def tearDown(self):
        self._home_patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # --- save_last_files / load_last_session_paths round-trip ---

    def test_save_last_files_creates_session_json(self):
        """Saving last-opened files produces a session.json with the correct paths."""
        paths = ["/data/run1.root", "/data/run2.root"]
        result = self.session_manager.save_last_files(paths)

        self.assertIsNotNone(result, "save_last_files should return the written path")
        self.assertTrue(os.path.isfile(result), "session.json file should exist on disk")

        with open(result, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        self.assertIn("last_files", data)
        self.assertEqual(len(data["last_files"]), 2)
        # Paths should be stored as absolute paths.
        for saved in data["last_files"]:
            self.assertTrue(os.path.isabs(saved),
                            f"Stored path should be absolute, got: {saved}")

    def test_load_last_session_paths_returns_existing_files(self):
        """After saving, load_last_session_paths returns only paths that exist on disk."""
        # Create two real temp files and one that does not exist.
        real1 = os.path.join(self._tmpdir, "a.root")
        real2 = os.path.join(self._tmpdir, "b.root")
        missing = os.path.join(self._tmpdir, "missing.root")
        with open(real1, "w"):
            pass
        with open(real2, "w"):
            pass

        self.session_manager.save_last_files([real1, real2, missing])

        # main._load_last_session_paths reads from session.json.
        from main import _load_last_session_paths
        loaded = _load_last_session_paths()

        self.assertIn(real1, loaded)
        self.assertIn(real2, loaded)
        self.assertNotIn(missing, loaded,
                         "Non-existent file should be filtered out on load")

    def test_session_round_trip_simulates_restart(self):
        """Saving open files before restart and reloading them simulates restart recovery."""
        real_file = os.path.join(self._tmpdir, "spectrum.root")
        with open(real_file, "w"):
            pass

        # ---- Before restart: save the open files ----
        self.session_manager.save_last_files([real_file])

        # ---- After restart: resolve initial paths ----
        from main import _resolve_initial_paths
        restored = _resolve_initial_paths(arg_path=None, use_last=True)

        self.assertIsNotNone(restored, "Should find files from the last session")
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0], real_file)

    def test_restart_with_no_session_returns_none(self):
        """With no session file, _resolve_initial_paths(use_last=True) returns None."""
        # No save_last_files call, so session.json does not exist.
        from main import _resolve_initial_paths
        result = _resolve_initial_paths(arg_path=None, use_last=True)
        self.assertIsNone(result)

    def test_autosave_writes_json(self):
        """auto_save_session silently writes a JSON autosave file."""
        filepath = self.session_manager.auto_save_session(
            histogram_name="test_hist",
            histogram_path="test_hist",
            fit_states={},
            peaks=[],
        )
        self.assertIsNotNone(filepath, "auto_save should return the saved file path")
        self.assertTrue(os.path.isfile(filepath))

        with open(filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["histogram"]["name"], "test_hist")

    def test_load_latest_autosave_returns_most_recent(self):
        """load_latest_autosave returns the most recently written autosave."""
        self.session_manager.auto_save_session("hist_a", "hist_a", {})
        import time
        time.sleep(0.05)  # ensure distinct mtime
        self.session_manager.auto_save_session("hist_b", "hist_b", {})

        latest = self.session_manager.load_latest_autosave()
        self.assertIsNotNone(latest)
        # The most recent autosave is for hist_b.
        self.assertEqual(latest["histogram"]["name"], "hist_b")


# ---------------------------------------------------------------------------
# 2. Tests for HistogramTab (opening, closing, switching)
# ---------------------------------------------------------------------------

class TestHistogramTabWorkflow(unittest.TestCase):
    """Tests exercising the HistogramTab open/close/switch workflow.

    The histogram tab interacts with tkinter widgets, so each test creates a
    minimal Tk root and patches the heavy renderer to avoid display-dependent
    ROOT rendering.
    """

    @classmethod
    def setUpClass(cls):
        """Create a single Tk root to share across all tests in this class."""
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

    def _make_histogram_tab(self):
        """Build a HistogramTab with a mock container and stub renderer."""
        import tkinter as tk
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramTab

        container = ttk.Frame(self._root)

        mock_app = MagicMock()
        mock_app.ROOT = _MOCK_ROOT

        selected_calls = []
        closed_calls = []
        opened_calls = []

        tab = HistogramTab(
            mock_app,
            container,
            on_histogram_selected=lambda key: selected_calls.append(key),
            on_histogram_closed=lambda count: closed_calls.append(count),
            on_histogram_opened=lambda lst: opened_calls.append(lst),
        )
        return tab, selected_calls, closed_calls, opened_calls

    def setUp(self):
        if not getattr(self, "_tk_available", False):
            self.skipTest("tkinter display not available")

    # ---- Opening multiple histograms ----

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_multiple_histograms(self, MockRenderer):
        """Opening three histograms registers all of them in the tab."""
        MockRenderer.return_value = MagicMock()

        tab, selected, closed, opened = self._make_histogram_tab()

        hists = [
            (_make_mock_histogram("h1"), "/data/run1.root", "h1"),
            (_make_mock_histogram("h2"), "/data/run1.root", "h2"),
            (_make_mock_histogram("h3"), "/data/run2.root", "h3"),
        ]
        for obj, root_path, path in hists:
            tab.open_histogram(obj, root_path, path)

        self.assertEqual(len(tab._hist_tabs), 3,
                         "Three distinct histograms should be open")
        self.assertEqual(len(tab._open_histograms), 3)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_same_histogram_twice_does_not_duplicate(self, MockRenderer):
        """Opening the same histogram twice should not create duplicate entries."""
        MockRenderer.return_value = MagicMock()

        tab, *_ = self._make_histogram_tab()
        obj = _make_mock_histogram("h1")
        tab.open_histogram(obj, "/data/run1.root", "h1")
        tab.open_histogram(obj, "/data/run1.root", "h1")

        self.assertEqual(len(tab._hist_tabs), 1)
        self.assertEqual(len(tab._open_histograms), 1)

    # ---- Closing histograms ----

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_current_histogram(self, MockRenderer):
        """close_current_histogram removes the displayed histogram."""
        MockRenderer.return_value = MagicMock()

        tab, selected, closed, opened = self._make_histogram_tab()
        obj = _make_mock_histogram("h1")
        tab.open_histogram(obj, "/data/run1.root", "h1")

        self.assertEqual(len(tab._hist_tabs), 1)
        tab.close_current_histogram()
        self.assertEqual(len(tab._hist_tabs), 0,
                         "Histogram should be removed after close")

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_all_histograms_one_by_one(self, MockRenderer):
        """Closing all histograms one by one empties the tab."""
        MockRenderer.return_value = MagicMock()

        tab, selected, closed, opened = self._make_histogram_tab()

        for i in range(3):
            tab.open_histogram(
                _make_mock_histogram(f"h{i}"),
                "/data/run.root",
                f"h{i}",
            )

        self.assertEqual(len(tab._hist_tabs), 3)

        # Close them by tab_key
        keys = [k for k, *_ in tab._open_histograms]
        for key in keys:
            tab.remove_histogram(key)

        self.assertEqual(len(tab._hist_tabs), 0)
        self.assertEqual(len(tab._open_histograms), 0)

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_close_histogram_fires_callback(self, MockRenderer):
        """Closing a histogram invokes the on_histogram_closed callback."""
        MockRenderer.return_value = MagicMock()

        tab, selected, closed, opened = self._make_histogram_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.open_histogram(_make_mock_histogram("h2"), "/data/run.root", "h2")

        tab.close_current_histogram()

        self.assertTrue(len(closed) > 0,
                        "on_histogram_closed callback should have been called")
        # After closing one of two, remaining count should be 1.
        self.assertEqual(closed[-1], 1)

    # ---- Opening more histograms after simulated session restore ----

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_open_more_histograms_after_close(self, MockRenderer):
        """After closing existing histograms, new ones can still be opened."""
        MockRenderer.return_value = MagicMock()

        tab, *_ = self._make_histogram_tab()
        tab.open_histogram(_make_mock_histogram("h1"), "/data/run.root", "h1")
        tab.close_current_histogram()
        self.assertEqual(len(tab._hist_tabs), 0)

        # Now open three more (simulating post-restart usage)
        for i in range(3):
            tab.open_histogram(
                _make_mock_histogram(f"new_h{i}"),
                "/data/new_run.root",
                f"new_h{i}",
            )

        self.assertEqual(len(tab._hist_tabs), 3)

    # ---- Switching between histograms ----

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_switch_between_histograms(self, MockRenderer):
        """show_histogram changes the current histogram key."""
        MockRenderer.return_value = MagicMock()

        tab, selected, *_ = self._make_histogram_tab()
        keys = []
        for i in range(3):
            obj = _make_mock_histogram(f"h{i}")
            root_path = "/data/run.root"
            path = f"h{i}"
            tab.open_histogram(obj, root_path, path)
            keys.append(f"{root_path}:{path}")

        # Switch to the first histogram
        tab.show_histogram(keys[0])
        self.assertEqual(tab._current_histogram_key, keys[0])

        # Switch to the last histogram
        tab.show_histogram(keys[2])
        self.assertEqual(tab._current_histogram_key, keys[2])

        # Switch back to the second histogram
        tab.show_histogram(keys[1])
        self.assertEqual(tab._current_histogram_key, keys[1])

    @patch("tab_managers.histogram_tab.HistogramPreviewRenderer")
    def test_switch_histogram_notifies_app(self, MockRenderer):
        """Opening a histogram always fires on_histogram_selected with the correct key."""
        MockRenderer.return_value = MagicMock()

        tab, selected, closed, opened = self._make_histogram_tab()
        obj1 = _make_mock_histogram("h1")
        obj2 = _make_mock_histogram("h2")
        tab.open_histogram(obj1, "/data/run.root", "h1")
        tab.open_histogram(obj2, "/data/run.root", "h2")

        expected_key1 = "/data/run.root:h1"
        expected_key2 = "/data/run.root:h2"

        self.assertIn(expected_key1, selected,
                      "on_histogram_selected should be called for h1")
        self.assertIn(expected_key2, selected,
                      "on_histogram_selected should be called for h2")


# ---------------------------------------------------------------------------
# 3. Tests for histogram control variables (axis ranges, log-scale toggles)
# ---------------------------------------------------------------------------

class TestHistogramControls(unittest.TestCase):
    """Tests for the axis range and log-scale controls on the preview renderer.

    These tests create a real tkinter root (hidden) so that DoubleVar /
    BooleanVar work correctly.  The heavy ROOT rendering is skipped by
    patching HistogramPreviewRenderer.render_preview.
    """

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
        """Build a HistogramPreviewRenderer with render patched out."""
        import tkinter as tk
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramPreviewRenderer

        renderer = HistogramPreviewRenderer()
        mock_app = MagicMock()
        mock_app.after.return_value = None
        mock_app.after_cancel.return_value = None
        mock_app.ROOT = _MOCK_ROOT

        container = ttk.Frame(self._root)
        with patch.object(renderer, "render_preview", return_value=None):
            renderer.build_histogram_tab(mock_app, container, obj, "/run.root", "h1")
        return renderer

    def test_initial_x_range_matches_histogram(self):
        """xmin / xmax variables are initialised from the histogram axis limits."""
        obj = _make_mock_histogram("h1", x_min=100.0, x_max=3000.0)
        renderer = self._build_renderer(obj)

        self.assertAlmostEqual(renderer._xmin_var.get(), 100.0, places=1)
        self.assertAlmostEqual(renderer._xmax_var.get(), 3000.0, places=1)

    def test_initial_log_y_is_enabled(self):
        """Log Y scale is enabled by default."""
        obj = _make_mock_histogram("h1")
        renderer = self._build_renderer(obj)
        self.assertTrue(renderer._logy_var.get(),
                        "Log Y should be True by default")

    def test_initial_log_x_is_disabled(self):
        """Log X scale is disabled by default."""
        obj = _make_mock_histogram("h1")
        renderer = self._build_renderer(obj)
        self.assertFalse(renderer._logx_var.get(),
                         "Log X should be False by default")

    def test_toggle_log_x(self):
        """Toggling Log X changes the BooleanVar state."""
        obj = _make_mock_histogram("h1")
        renderer = self._build_renderer(obj)
        self.assertFalse(renderer._logx_var.get())
        renderer._logx_var.set(True)
        self.assertTrue(renderer._logx_var.get())
        renderer._logx_var.set(False)
        self.assertFalse(renderer._logx_var.get())

    def test_toggle_log_y(self):
        """Toggling Log Y changes the BooleanVar state."""
        obj = _make_mock_histogram("h1")
        renderer = self._build_renderer(obj)
        initial = renderer._logy_var.get()
        renderer._logy_var.set(not initial)
        self.assertNotEqual(renderer._logy_var.get(), initial)

    def test_set_x_range(self):
        """Setting xmin / xmax variables stores the provided values."""
        obj = _make_mock_histogram("h1", x_min=0.0, x_max=1000.0)
        renderer = self._build_renderer(obj)

        renderer._xmin_var.set(200.0)
        renderer._xmax_var.set(800.0)

        self.assertAlmostEqual(renderer._xmin_var.get(), 200.0, places=1)
        self.assertAlmostEqual(renderer._xmax_var.get(), 800.0, places=1)

    def test_set_y_range(self):
        """Setting ymin / ymax variables stores the provided values."""
        obj = _make_mock_histogram("h1", y_min=1.0, y_max=1000.0)
        renderer = self._build_renderer(obj)

        renderer._ymin_var.set(5.0)
        renderer._ymax_var.set(500.0)

        self.assertAlmostEqual(renderer._ymin_var.get(), 5.0, places=1)
        self.assertAlmostEqual(renderer._ymax_var.get(), 500.0, places=1)

    def test_controls_for_multiple_histograms_are_independent(self):
        """Each histogram renderer has its own independent set of control variables."""
        from tab_managers.histogram_tab import HistogramPreviewRenderer
        from tkinter import ttk

        obj1 = _make_mock_histogram("h1", x_min=0.0, x_max=500.0)
        obj2 = _make_mock_histogram("h2", x_min=0.0, x_max=2000.0)

        renderer1 = self._build_renderer(obj1)
        renderer2 = self._build_renderer(obj2)

        # Modify renderer1's x range; renderer2 should be unaffected.
        renderer1._xmax_var.set(300.0)

        self.assertAlmostEqual(renderer1._xmax_var.get(), 300.0, places=1)
        self.assertAlmostEqual(renderer2._xmax_var.get(), 2000.0, places=1)


# ---------------------------------------------------------------------------
# 4. Integration-style test: full open → close → restart → open → control flow
# ---------------------------------------------------------------------------

class TestFullWorkflow(unittest.TestCase):
    """Higher-level scenario test that chains the individual steps together."""

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
        self._home_patcher = patch("os.path.expanduser",
                                   side_effect=lambda p: p.replace("~", self._tmpdir))
        self._home_patcher.start()

        from modules.session_manager import SessionManager
        self.session_manager = SessionManager()

    def tearDown(self):
        self._home_patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_histogram_tab(self):
        from tkinter import ttk
        from tab_managers.histogram_tab import HistogramTab
        container = ttk.Frame(self._root)
        mock_app = MagicMock()
        mock_app.ROOT = _MOCK_ROOT
        return HistogramTab(mock_app, container)

    def test_open_close_restart_open_switch(self):
        """
        Full scenario:
          1. Open three histograms.
          2. Close two of them.
          3. Save session (simulate restart).
          4. Restore session paths and open three more histograms.
          5. Play with controls on a renderer.
          6. Switch between all open histograms.
        """
        # Use a context manager so the patch applies only to the tab steps,
        # leaving the real HistogramPreviewRenderer available for Step 5.
        mock_renderer_instance = MagicMock()
        renderer_patch = patch(
            "tab_managers.histogram_tab.HistogramPreviewRenderer",
            return_value=mock_renderer_instance,
        )

        with renderer_patch:
            # --- Step 1: Open three histograms ---
            tab = self._make_histogram_tab()
            root_path = "/data/first_run.root"
            initial_hists = ["spectrum_A", "spectrum_B", "spectrum_C"]
            for name in initial_hists:
                tab.open_histogram(_make_mock_histogram(name), root_path, name)

            self.assertEqual(len(tab._hist_tabs), 3, "Step 1: three histograms open")

            # --- Step 2: Close two histograms ---
            keys_to_close = [f"{root_path}:{initial_hists[0]}",
                             f"{root_path}:{initial_hists[1]}"]
            for key in keys_to_close:
                tab.remove_histogram(key)

            self.assertEqual(len(tab._hist_tabs), 1, "Step 2: one histogram remains")

            # --- Step 3: Save session (simulated restart) ---
            real_file = os.path.join(self._tmpdir, "first_run.root")
            with open(real_file, "w"):
                pass
            self.session_manager.save_last_files([real_file])

            from main import _resolve_initial_paths
            restored_paths = _resolve_initial_paths(arg_path=None, use_last=True)
            self.assertIsNotNone(restored_paths, "Step 3: session should restore paths")
            self.assertIn(real_file, restored_paths)

            # --- Step 4: Open three more histograms (post-restart) ---
            second_root = "/data/second_run.root"
            post_restart_hists = ["gamma_1", "gamma_2", "gamma_3"]
            for name in post_restart_hists:
                tab.open_histogram(_make_mock_histogram(name), second_root, name)

            # 1 remaining from before + 3 new = 4
            self.assertEqual(len(tab._hist_tabs), 4,
                             "Step 4: four histograms open after post-restart additions")

        # --- Step 5: Play with controls (use real HistogramPreviewRenderer) ---
        from tab_managers.histogram_tab import HistogramPreviewRenderer
        from tkinter import ttk

        real_renderer = HistogramPreviewRenderer()
        mock_app_ctrl = MagicMock()
        mock_app_ctrl.after.return_value = None
        mock_app_ctrl.after_cancel.return_value = None
        mock_app_ctrl.ROOT = _MOCK_ROOT
        ctrl_container = ttk.Frame(self._root)
        ctrl_obj = _make_mock_histogram("gamma_1", x_min=10.0, x_max=2000.0)
        with patch.object(real_renderer, "render_preview", return_value=None):
            real_renderer.build_histogram_tab(
                mock_app_ctrl, ctrl_container, ctrl_obj, second_root, "gamma_1"
            )

        # Zoom in on X axis
        real_renderer._xmin_var.set(100.0)
        real_renderer._xmax_var.set(1500.0)
        self.assertAlmostEqual(real_renderer._xmin_var.get(), 100.0, places=1)
        self.assertAlmostEqual(real_renderer._xmax_var.get(), 1500.0, places=1)

        # Toggle log scales
        real_renderer._logx_var.set(True)
        real_renderer._logy_var.set(False)
        self.assertTrue(real_renderer._logx_var.get(), "Step 5: log X toggled on")
        self.assertFalse(real_renderer._logy_var.get(), "Step 5: log Y toggled off")

        # --- Step 6: Switch between histograms ---
        all_keys = [k for k, *_ in tab._open_histograms]
        self.assertGreaterEqual(len(all_keys), 2,
                                "Step 6: at least two histograms to switch between")
        for key in all_keys:
            tab.show_histogram(key)
            self.assertEqual(tab._current_histogram_key, key,
                             f"Step 6: current key should be {key}")


if __name__ == "__main__":
    unittest.main()

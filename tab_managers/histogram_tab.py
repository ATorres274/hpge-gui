from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from modules.error_dispatcher import get_dispatcher, ErrorLevel
from modules.preview_manager import HistogramRenderer
from tab_managers.histogram_preview_renderer import HistogramPreviewRenderer

# Re-export so existing imports of the form
#   ``from tab_managers.histogram_tab import HistogramPreviewRenderer``
# continue to work without modification.
__all__ = ["HistogramTab", "HistogramPreviewRenderer"]

class HistogramTab:
    """Histogram tab view - manages multiple histogram previews and controls.

    This tab creates a simple container for each opened histogram
    and delegates preview UI creation to `HistogramPreviewRenderer`. It intentionally
    keeps behavior minimal so modules can be re-attached incrementally.
    
    Callbacks (provided by app for visibility orchestration):
    - on_histogram_selected(tab_key: str) - called when user selects a histogram
    - on_histogram_closed(remaining_count: int) - called when histogram is closed
    """

    def __init__(self, app, hist_container: ttk.Frame, 
                 on_histogram_selected=None, on_histogram_closed=None, on_histogram_opened=None):
        self.app = app
        self._hist_container = hist_container
        self._dispatcher = get_dispatcher()
        
        # Callbacks from app for orchestration (not hooks, formal interface)
        self._on_histogram_selected = on_histogram_selected
        self._on_histogram_closed = on_histogram_closed
        self._on_histogram_opened = on_histogram_opened

        # Shared preview renderer for this manager
        try:
            self._preview_manager = HistogramRenderer()
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to initialize HistogramRenderer",
                context="HistogramTab",
                exception=e
            )
            self._preview_manager = None

        # store (container, renderer, obj) tuples for each open histogram
        self._hist_tabs: dict[str, tuple[ttk.Frame, object, object]] = {}
        self._open_histograms: list[tuple[str, str, str]] = []
        self._current_histogram_key: str | None = None

    @property
    def current_histogram_key(self) -> str | None:
        """Return the key of the currently displayed histogram, or None."""
        return self._current_histogram_key

    def open_histogram(self, obj, root_path: str, path: str) -> None:
        tab_key = f"{root_path}:{path}"
        hist_name = getattr(obj, 'GetName', lambda: 'hist')()
        file_name = os.path.basename(root_path) or root_path
        display_name = f"{file_name} / {hist_name}"

        if tab_key in self._hist_tabs:
            self.show_histogram(tab_key)
            # Notify app of selection even if histogram already exists
            if self._on_histogram_selected and callable(self._on_histogram_selected):
                try:
                    self._on_histogram_selected(tab_key)
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to notify app of histogram selection",
                        context="HistogramTab.open_histogram",
                        exception=e
                    )
            return

        container = ttk.Frame(self._hist_container)
        renderer = HistogramPreviewRenderer()
        # give renderer access to the preview manager so it can render into
        # its local preview label.
        try:
            renderer._preview_manager = self._preview_manager
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to assign preview manager to renderer",
                context="HistogramTab.open_histogram",
                exception=e
            )
            renderer._preview_manager = None

        renderer.build_histogram_tab(self.app, container, obj, root_path, path)
        # Render a preview for this histogram via the preview manager.
        try:
            renderer.render_preview(obj)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to render histogram preview",
                context="HistogramTab.open_histogram",
                exception=e
            )

        # store obj so we can re-render when the tab is shown
        self._hist_tabs[tab_key] = (container, renderer, obj)
        self._open_histograms.append((tab_key, display_name, root_path))
        
        # Notify app of new histogram
        if self._on_histogram_opened and callable(self._on_histogram_opened):
            try:
                self._on_histogram_opened([(k, n) for k, n, _ in self._open_histograms])
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram opened",
                    context="HistogramTab.open_histogram",
                    exception=e
                )
        
        self.show_histogram(tab_key)
        
        # Notify app of selection
        if self._on_histogram_selected and callable(self._on_histogram_selected):
            try:
                self._on_histogram_selected(tab_key)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram selection",
                    context="HistogramTab.open_histogram",
                    exception=e
                )

    def show_histogram(self, tab_key: str) -> None:
        if tab_key not in self._hist_tabs:
            return
        # hide others (unconditionally, even if not currently mapped, so they don't
        # reappear when _hist_container is re-packed after returning from the browser)
        for k, v in self._hist_tabs.items():
            c = v[0]
            if k != tab_key:
                c.pack_forget()

        container, renderer, obj = self._hist_tabs[tab_key]
        if not self._hist_container.winfo_ismapped():
            try:
                self._hist_container.pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to pack histogram container",
                    context="HistogramTab.show_histogram",
                    exception=e
                )
        if not container.winfo_ismapped():
            try:
                container.pack(fill=tk.BOTH, expand=True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to pack histogram tab container",
                    context="HistogramTab.show_histogram",
                    exception=e
                )

        self._current_histogram_key = tab_key

        # Render preview if renderer is ready
        try:
            renderer.render_preview(obj)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to render preview when showing histogram",
                context="HistogramTab.show_histogram",
                exception=e
            )

    def hide_all_histograms(self) -> None:
        """Hide all open histogram containers and clear current selection."""
        try:
            for c, renderer, obj in self._hist_tabs.values():
                try:
                    if c.winfo_ismapped():
                        c.pack_forget()
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to hide histogram container",
                        context="HistogramTab.hide_all_histograms",
                        exception=e
                    )
            try:
                if self._hist_container.winfo_ismapped():
                    self._hist_container.pack_forget()
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to hide histogram tab container",
                    context="HistogramTab.hide_all_histograms",
                    exception=e
                )
            self._current_histogram_key = None
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to hide all histograms",
                context="HistogramTab.hide_all_histograms",
                exception=e
            )

    def on_histogram_selected(self) -> None:
        """User selected a histogram from within the manager.
        
        Notify the app via callback so it can orchestrate visibility.
        """
        # Notify app of selection (app orchestrates visibility)
        if self._on_histogram_selected and callable(self._on_histogram_selected):
            try:
                # Get the selected histogram key from _open_histograms
                # This is called from app when combo changes
                if hasattr(self, '_pending_selection'):
                    tab_key = self._pending_selection
                    delattr(self, '_pending_selection')
                    self._on_histogram_selected(tab_key)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to notify app of histogram selection",
                    context="HistogramTab.on_histogram_selected",
                    exception=e
                )

    def close_current_histogram(self) -> None:
        """Close the currently displayed histogram."""
        if self._current_histogram_key and self._current_histogram_key in self._hist_tabs:
            self.remove_histogram(self._current_histogram_key)

    def remove_histogram(self, tab_key: str) -> None:
        """Remove a histogram from the tab."""
        if tab_key not in self._hist_tabs:
            return
        
        try:
            # Remember the index of the histogram being closed before removing it
            closed_idx = next(
                (i for i, (k, _, _) in enumerate(self._open_histograms) if k == tab_key),
                -1,
            )

            # Remove from tracking
            container, renderer, obj = self._hist_tabs[tab_key]
            # Unpack the container explicitly before removing from tracking so that
            # hide_all_histograms (called below when closing the current histogram)
            # does not leave this container packed after it is no longer tracked.
            try:
                container.pack_forget()
            except Exception:
                pass
            del self._hist_tabs[tab_key]
            
            # Remove from dropdown list
            self._open_histograms = [(k, n, p) for k, n, p in self._open_histograms if k != tab_key]
            
            # Update dropdown via app callback
            if hasattr(self, '_app') and hasattr(self._app, 'update_histogram_dropdown'):
                try:
                    self._app.update_histogram_dropdown([(k, n) for k, n, _ in self._open_histograms])
                except Exception:
                    pass
            
            # Clear as current if it was
            if self._current_histogram_key == tab_key:
                self._current_histogram_key = None
                if self._open_histograms:
                    # Show the next histogram in sequence (or the previous one if the
                    # closed histogram was the last entry in the list).
                    next_idx = min(closed_idx, len(self._open_histograms) - 1)
                    next_key = self._open_histograms[next_idx][0]
                    self.show_histogram(next_key)
                else:
                    self.hide_all_histograms()

            # Notify app of remaining count via callback
            remaining = len(self._hist_tabs)
            if self._on_histogram_closed and callable(self._on_histogram_closed):
                try:
                    self._on_histogram_closed(remaining)
                except Exception:
                    pass
        except Exception:
            pass

    def remove_histogram_by_index(self, idx: int) -> None:
        """Remove a histogram by its dropdown index."""
        if idx < 0 or idx >= len(self._open_histograms):
            return
        tab_key, _, _ = self._open_histograms[idx]
        self.remove_histogram(tab_key)



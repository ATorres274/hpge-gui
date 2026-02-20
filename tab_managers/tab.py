"""Tab base class for tab manager implementations.

This lives under `tab_managers` so tabs can import it without
depending on the `modules` layer.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

class Tab:
    """Minimal base class for tab-like UI components.

    Subclassers may override `build_ui`, `on_selection`, and
    `on_file_opened` as needed. This intentionally stays small so
    different tab implementations can remain lightweight.
    """

    name: str = "Tab"

    def build_ui(self, app, parent: ttk.Frame) -> None:
        """Construct UI for this tab inside `parent`.

        Implementations should create and pack widgets into `parent`.
        """
        raise NotImplementedError()

    def on_selection(self, app, obj, path: str) -> None:
        """Called when an object is selected for this tab (optional)."""
        return None

    def on_file_opened(self, app, root_file) -> None:
        """Called when a file is opened in the application (optional)."""
        return None

__all__ = ["Tab"]

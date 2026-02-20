#!/usr/bin/env python3
"""Application shell - minimal UI framework that delegates to tab managers.

This module contains only the base application window, top bar, and container management.
All feature-specific logic is delegated to tab managers (browser, histogram, fitting, etc.).

Architecture:
- App owns: top bar UI, tab initialization, visibility orchestration, event routing
- Tabs own: their UI layout, internal module coordination
- Modules own: domain logic, delegating to features
- Features own: pure action handlers, no UI or state

All communication flows: App → Tab → Module → Feature (one direction only)
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from tab_managers.tab_registry import registry as tab_registry
from modules.error_dispatcher import ErrorDispatcher, ErrorLevel

try:
    import ROOT  # PyROOT
except Exception as exc:  # pragma: no cover
    ROOT = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

class RootBrowserApp(tk.Tk):
    """Main application window - minimal shell that delegates to tab managers.
    
    Responsibilities:
    - Top-level UI (navigation buttons, histogram dropdown, close button)
    - Tab initialization and lifecycle
    - Visibility orchestration (showing/hiding browser vs histogram)
    - Event routing between tabs via callbacks
    """
    
    def __init__(self, initial_paths: list[str] | None = None) -> None:
        super().__init__()
        self.title("PyROOT Browser")
        self.geometry("1280x720")

        self._icon_image: tk.PhotoImage | None = None
        self._set_app_icon()

        # Core references
        self.ROOT = ROOT
        
        # Set up error dispatcher and subscribe to error events
        self._error_dispatcher = ErrorDispatcher.get_instance()
        self._error_dispatcher.subscribe(ErrorLevel.ERROR, self._on_error)
        self._error_dispatcher.subscribe(ErrorLevel.CRITICAL, self._on_critical_error)
        
        # Build UI and initialize
        self._build_ui()
        
        # Initialize browser tab with callbacks for coordination
        try:
            self.browser_tab = tab_registry.create(
                "browser",
                ROOT,
                self._open_file_btn,
                on_histogram_opening=self._on_browser_histogram_opening,
                on_directory_opened=self._on_browser_directory_opened,
                on_selection_changed=self._on_browser_selection_changed,
                on_focus_changed=self._on_browser_focus_changed,
            )
        except Exception as e:
            # Fallback to direct import if registry isn't available
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Registry failed to create browser tab, using direct import",
                context="AppShell.__init__",
                exception=e
            )
            from tab_managers.browser_tab import BrowserTab as _BrowserTab
            self.browser_tab = _BrowserTab(
                ROOT,
                self._open_file_btn,
                on_histogram_opening=self._on_browser_histogram_opening,
                on_directory_opened=self._on_browser_directory_opened,
                on_selection_changed=self._on_browser_selection_changed,
                on_focus_changed=self._on_browser_focus_changed,
            )
        browser_frame = self.browser_tab.build_ui(self._main_container)
        browser_frame.pack(fill=tk.BOTH, expand=True)
        
        # Expose details_frame from browser tab so features can render into it
        try:
            self.details_frame = self.browser_tab.detail_container
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to get details_frame from browser tab",
                context="AppShell.__init__",
                exception=e
            )
        
        # Initialize histogram tab with callbacks to app for orchestration
        try:
            self.histogram_tab = tab_registry.create(
                "histogram_tab",
                self,
                self._hist_container,
                on_histogram_selected=self._on_histogram_selected,
                on_histogram_closed=self._on_histogram_closed,
                on_histogram_opened=self._on_histogram_opened,
            )
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Registry failed to create histogram tab, using direct import",
                context="AppShell.__init__",
                exception=e
            )
            from tab_managers.histogram_tab import HistogramTab as _HistogramTab
            self.histogram_tab = _HistogramTab(
                self,
                self._hist_container,
                on_histogram_selected=self._on_histogram_selected,
                on_histogram_closed=self._on_histogram_closed,
                on_histogram_opened=self._on_histogram_opened,
            )
        
        # Initial focus
        self._focus_browser()
        self.after(50, self._maximize_on_primary_screen)
        self.after(100, self._maximize_on_primary_screen)

        # Handle ROOT import errors and initial files
        if ROOT is None:
            messagebox.showerror(
                "PyROOT not available",
                f"Failed to import ROOT: {_IMPORT_ERROR}\n\n"
                "Install ROOT with PyROOT enabled, then retry.",
            )
        elif initial_paths:
            self.after(100, lambda: self.browser_tab.open_paths(initial_paths))
        # Attempt to restore tree state from latest autosave (best-effort)
        try:
            self.after(200, self.browser_tab.apply_autosave)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to schedule autosave restore",
                context="AppShell.__init__",
                exception=e
            )

    def _apply_latest_autosave(self) -> None:
        """Load the most recent autosave session and apply its tree state."""
        try:
            if not hasattr(self, 'session_manager') or not self.session_manager:
                return
            data = self.session_manager.load_latest_autosave()
            if not data:
                return
            try:
                file_manager = None
                try:
                    file_manager = self.browser_manager.module_registry.get('file_manager')
                except Exception:
                    file_manager = None
                self.session_manager.apply_tree_state(data, getattr(self.browser_manager, 'tree', None), file_manager=file_manager)
            except Exception:
                pass
        except Exception:
            pass

    def _maximize_on_primary_screen(self) -> None:
        """Maximize window on primary screen."""
        try:
            self.update_idletasks()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w}x{screen_h}+0+0")
            try:
                self.state("zoomed")
            except tk.TclError as e:
                self._error_dispatcher.emit(
                    ErrorLevel.INFO,
                    "Could not set window state to zoomed",
                    context="AppShell._maximize_on_primary_screen",
                    exception=e
                )
        except tk.TclError as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to maximize window on primary screen",
                context="AppShell._maximize_on_primary_screen",
                exception=e
            )

    def _set_app_icon(self) -> None:
        """Set application icon from assets folder."""
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "app_icon.png")
        if not os.path.isfile(icon_path):
            return

        try:
            self._icon_image = tk.PhotoImage(file=icon_path)
            self.iconphoto(True, self._icon_image)
        except tk.TclError as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                f"Failed to load app icon from {icon_path}",
                context="AppShell._set_app_icon",
                exception=e
            )

    def _build_ui(self) -> None:
        """Build the minimal application shell UI."""
        top_panel = ttk.Frame(self)
        top_panel.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Top bar with navigation and controls
        top_bar = ttk.Frame(top_panel)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_bar, text="🏠 Home", command=self._focus_browser).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(top_bar, text="Restart", command=self._restart_app).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self._open_file_btn = ttk.Button(top_bar, text="Open ROOT File")
        self._open_file_btn.pack(side=tk.LEFT)

        # Histogram selector dropdown (app owns this UI)
        ttk.Label(top_bar, text="Histogram:").pack(side=tk.LEFT, padx=(12, 4))
        self._histogram_var = tk.StringVar(value="")
        self._histogram_combo = ttk.Combobox(
            top_bar,
            textvariable=self._histogram_var,
            state="readonly",
            width=50,
        )
        self._histogram_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._histogram_combo.bind("<<ComboboxSelected>>", self._on_histogram_combo_selected)
        
        self._close_histogram_btn = ttk.Button(top_bar, text="✕ Close")
        self._close_histogram_btn.pack(side=tk.LEFT, padx=(0, 4))
        self._close_histogram_btn.configure(command=self._on_close_histogram_btn)

        # Main container for histogram and browser content
        self._main_container = ttk.Frame(top_panel)
        self._main_container.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        
        # Histogram container (will be shown when histograms are open)
        self._hist_container = ttk.Frame(self._main_container)

    # Error Handling

    def _on_browser_histogram_opening(self, obj, root_path: str, path: str) -> None:
        """Callback from browser tab when a histogram is double-clicked.
        
        Opens the histogram in the histogram tab.
        """
        try:
            if hasattr(self, 'histogram_tab') and self.histogram_tab:
                self.histogram_tab.open_histogram(obj, root_path, path)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.ERROR,
                "Failed to open histogram from browser",
                context="AppShell._on_browser_histogram_opening",
                exception=e
            )

    def _on_browser_directory_opened(self, directory, path: str) -> None:
        """Callback from browser tab when a directory is opened.
        
        Notifies feature registry of directory open event.
        """
        try:
            if hasattr(self, 'feature_registry') and self.feature_registry:
                self.feature_registry.notify_directory_opened(self, directory, path)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to notify feature registry of directory open",
                context="AppShell._on_browser_directory_opened",
                exception=e
            )

    def _on_browser_selection_changed(self, obj, path: str) -> None:
        """Callback from browser tab when tree selection changes.
        
        Notifies feature registry and shows details panel.
        """
        try:
            if hasattr(self, 'feature_registry') and self.feature_registry:
                self.feature_registry.notify_selection(self, obj, path)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to notify feature registry of selection change",
                context="AppShell._on_browser_selection_changed",
                exception=e
            )

    def _on_browser_focus_changed(self, visible: bool) -> None:
        """Callback from browser tab when browser focus changes.
        
        If browser is gaining focus, hide any open histograms.
        """
        try:
            if visible and hasattr(self, 'histogram_tab') and self.histogram_tab:
                self.histogram_tab.hide_all_histograms()
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to hide histograms when browser gained focus",
                context="AppShell._on_browser_focus_changed",
                exception=e
            )

    def _on_histogram_opened(self, histogram_list: list[tuple[str, str]]) -> None:
        """Callback from histogram tab when a new histogram is opened.
        
        Updates the histogram dropdown combobox.
        
        Args:
            histogram_list: List of (key, display_name) tuples for open histograms
        """
        try:
            self.update_histogram_dropdown(histogram_list)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to update histogram dropdown when new histogram opened",
                context="AppShell._on_histogram_opened",
                exception=e
            )

    # Error Handling

    def _on_error(self, error_event) -> None:
        """Handle ERROR level errors - show message box to user."""
        try:
            # Build detailed error message
            detail_lines = [f"{error_event.context}: {error_event.message}"]
            if error_event.exception:
                detail_lines.append(f"\nException: {type(error_event.exception).__name__}")
                detail_lines.append(str(error_event.exception))
            detail_message = "\n".join(detail_lines)
            
            messagebox.showerror(
                "Error",
                detail_message
            )
        except Exception as e:
            # If messagebox fails, try to log to stderr at least
            import sys
            print(f"ERROR DIALOG FAILED: {error_event.context}: {error_event.message}", file=sys.stderr)
            print(f"Dialog exception: {e}", file=sys.stderr)

    def _on_critical_error(self, error_event) -> None:
        """Handle CRITICAL level errors - show error and potentially exit."""
        try:
            # Build detailed error message
            detail_lines = [f"{error_event.context}: {error_event.message}"]
            if error_event.exception:
                detail_lines.append(f"\nException: {type(error_event.exception).__name__}")
                detail_lines.append(str(error_event.exception))
            detail_lines.append("\nThe application may be in an unstable state.")
            detail_message = "\n".join(detail_lines)
            
            messagebox.showerror(
                "Critical Error",
                detail_message
            )
        except Exception as e:
            # If messagebox fails, try to log to stderr at least
            import sys
            print(f"CRITICAL ERROR DIALOG FAILED: {error_event.context}: {error_event.message}", file=sys.stderr)
            print(f"Dialog exception: {e}", file=sys.stderr)

    # Event Handlers (App orchestrates visibility and routing)

    def _on_histogram_combo_selected(self, event=None) -> None:
        """User selected a histogram from the dropdown. App orchestrates visibility."""
        try:
            # Get selected histogram key from combo
            idx = self._histogram_combo.current()
            if idx < 0:
                return
            
            # Retrieve the histogram key from the tab
            if hasattr(self.histogram_tab, '_open_histograms') and idx < len(self.histogram_tab._open_histograms):
                tab_key, _, _ = self.histogram_tab._open_histograms[idx]
                # Clear combo selection highlight
                try:
                    self._histogram_combo.selection_clear()
                except Exception as e:
                    self._error_dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to clear combo selection",
                        context="AppShell._on_histogram_combo_selected",
                        exception=e
                    )
                # Show the histogram (app owns this decision)
                self._show_histogram(tab_key)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Error handling histogram combo selection",
                context="AppShell._on_histogram_combo_selected",
                exception=e
            )

    def _on_histogram_selected(self, tab_key: str) -> None:
        """Callback from histogram tab when user selects a histogram internally.
        
        This allows the tab to inform the app of selection changes,
        but the app orchestrates the visibility change.
        """
        try:
            # Update combo to reflect selection
            if hasattr(self.histogram_tab, '_open_histograms'):
                for idx, (key, _, _) in enumerate(self.histogram_tab._open_histograms):
                    if key == tab_key:
                        self._histogram_combo.current(idx)
                        break
            # Show the histogram
            self._show_histogram(tab_key)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                f"Error handling histogram selection for {tab_key}",
                context="AppShell._on_histogram_selected",
                exception=e
            )

    def _on_histogram_closed(self, remaining_count: int, histogram_list: list = None) -> None:
        """Callback from histogram tab when a histogram is closed.

        Updates the dropdown with remaining histograms.  If another histogram
        is still being displayed it updates the combobox selection to match it.
        If no histograms remain, returns the user to the browser.
        """
        try:
            # Update the dropdown values to reflect remaining histograms
            if histogram_list is not None:
                self.update_histogram_dropdown(histogram_list)

            if not self._hist_container.winfo_ismapped():
                # No histogram is visible – go to browser (clears combo selection)
                self._focus_browser()
            else:
                # A histogram is still on screen; sync the combo selection to it
                current_key = (
                    self.histogram_tab.current_histogram_key
                    if hasattr(self, 'histogram_tab')
                    else None
                )
                if current_key and histogram_list:
                    for idx, (k, _) in enumerate(histogram_list):
                        if k == current_key:
                            try:
                                self._histogram_combo.current(idx)
                            except Exception:
                                pass
                            break
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                f"Error handling histogram closed event (remaining={remaining_count})",
                context="AppShell._on_histogram_closed",
                exception=e
            )

    def _on_close_histogram_btn(self) -> None:
        """User clicked close button on histogram dropdown. App orchestrates cleanup."""
        try:
            # Determine what's visible and close appropriately
            if self._hist_container.winfo_ismapped():
                # Histogram is visible, close it
                try:
                    self.histogram_tab.close_current_histogram()
                except Exception as e:
                    self._error_dispatcher.emit(
                        ErrorLevel.WARNING,
                        "Failed to close current histogram",
                        context="AppShell._on_close_histogram_btn",
                        exception=e
                    )
            else:
                # Browser is visible, close selected histogram in background
                try:
                    idx = self._histogram_combo.current()
                    if idx >= 0:
                        self.histogram_tab.remove_histogram_by_index(idx)
                except Exception as e:
                    self._error_dispatcher.emit(
                        ErrorLevel.WARNING,
                        f"Failed to remove histogram at index {idx}",
                        context="AppShell._on_close_histogram_btn",
                        exception=e
                    )
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.ERROR,
                "Error in close histogram button handler",
                context="AppShell._on_close_histogram_btn",
                exception=e
            )

    # Navigation (App owns visibility orchestration)

    def _show_histogram(self, tab_key: str) -> None:
        """Show a specific histogram and hide the browser.
        
        App owns this orchestration, not the histogram tab.
        """
        try:
            # Hide browser
            if hasattr(self, 'browser_tab'):
                self.browser_tab.hide()
            # Show histogram
            self.histogram_tab.show_histogram(tab_key)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.ERROR,
                f"Failed to show histogram {tab_key}",
                context="AppShell._show_histogram",
                exception=e
            )

    def _focus_browser(self) -> None:
        """Show browser and hide histograms. App owns this orchestration."""
        try:
            # Hide histogram container
            if self._hist_container.winfo_ismapped():
                self._hist_container.pack_forget()
            # Show browser
            if hasattr(self, 'browser_tab'):
                self.browser_tab.focus()
            # Clear combo selection
            try:
                self._histogram_combo.set("")
            except Exception as e:
                self._error_dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to clear histogram combo",
                    context="AppShell._focus_browser",
                    exception=e
                )
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to focus browser",
                context="AppShell._focus_browser",
                exception=e
            )

    def update_histogram_dropdown(self, histogram_list: list[tuple[str, str]]) -> None:
        """Update the histogram dropdown with new histogram entries.
        
        Called by histogram_manager to notify app of dropdown changes.
        App owns the combo box UI, so it updates the display.
        """
        try:
            display_names = [name for _, name in histogram_list]
            self._histogram_combo['values'] = display_names
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to update histogram dropdown",
                context="AppShell.update_histogram_dropdown",
                exception=e
            )

    # Utility

    def _restart_app(self) -> None:
        """Restart the application."""
        try:
            python = sys.executable
            if not python:
                self._error_dispatcher.emit(
                    ErrorLevel.WARNING,
                    "Could not find Python executable",
                    context="AppShell._restart_app"
                )
                return
            # Save last-opened files before restarting so --last loads them
            try:
                self.browser_tab.save_session_on_restart()
            except Exception as e:
                self._error_dispatcher.emit(
                    ErrorLevel.WARNING,
                    "Failed to save session before restart",
                    context="AppShell._restart_app",
                    exception=e
                )

            # Always use --last flag on restart to restore session
            args = [python] + [sys.argv[0], "--last"]
            self.destroy()
            os.execv(python, args)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.ERROR,
                "Failed to restart application",
                context="AppShell._restart_app",
                exception=e
            )

    # Cleanup

    def destroy(self) -> None:
        """Clean up resources before closing."""
        self._cleanup()
        super().destroy()

    def _cleanup(self) -> None:
        """Clean up temporary files and resources."""
        # Auto-save session on application close (best-effort)
        try:
            hist_name = "app"
            hist_path = ""
            
            # Extract histogram info from current state if available
            try:
                if hasattr(self, 'histogram_tab') and self.histogram_tab:
                    if hasattr(self.histogram_tab, '_current_histogram_key') and self.histogram_tab._current_histogram_key:
                        key = self.histogram_tab._current_histogram_key
                        parts = key.split(":", 1)
                        if parts:
                            hist_name = parts[0]
                            hist_path = parts[1] if len(parts) > 1 else ""
            except Exception:
                pass
            
            self.browser_tab.auto_save_session(hist_name, hist_path)
        except Exception as e:
            self._error_dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to auto-save session on close",
                context="AppShell._cleanup",
                exception=e
            )

        if hasattr(self, "browser_tab") and self.browser_tab:
            try:
                self.browser_tab.cleanup()
            except Exception as e:
                self._error_dispatcher.emit(
                    ErrorLevel.WARNING,
                    "Failed to cleanup browser tab",
                    context="AppShell._cleanup",
                    exception=e
                )


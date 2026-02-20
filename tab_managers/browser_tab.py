"""Browser tab manager - handles ROOT file browsing and navigation.

This module contains all file browser logic previously in app_shell.py.
It manages the tree view, file opening, directory navigation, and object selection.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from modules.root_file_manager import RootFileManager
from modules.module_registry import ModuleRegistry
from modules.session_manager import SessionManager
from modules.error_dispatcher import get_dispatcher, ErrorLevel

class BrowserTab:
    @property
    def _open_root_files(self):
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            return file_manager._open_root_files
        return {}

    def open_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        """Delegate opening multiple ROOT file paths to RootFileManager (calls open_path for each)."""
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            for path in paths:
                file_manager.open_path(path, self.tree, self._populate_directory)
    """Manages the ROOT file browser interface."""

    def __init__(self, root_module, open_file_btn: ttk.Button | None = None, close_file_btn: ttk.Button | None = None,
                 on_histogram_opening=None, on_directory_opened=None, on_selection_changed=None,
                 on_focus_changed=None):
        """
        Initialize BrowserTab.
        
        Args:
            root_module: PyROOT module reference
            open_file_btn: Button for opening files (optional)
            close_file_btn: Button for closing files (optional)
            on_histogram_opening: Callback(obj, root_path, path) when histogram is double-clicked
            on_directory_opened: Callback(directory, path) when directory node is expanded
            on_selection_changed: Callback(obj, path) when tree node is selected
            on_focus_changed: Callback(visible: bool) when browser focus changes
        """
        self.ROOT = root_module
        self.module_registry = ModuleRegistry()
        self._dispatcher = get_dispatcher()
        self.tree: ttk.Treeview | None = None
        self.detail_container: ttk.Frame | None = None
        self.browser_frame: ttk.Frame | None = None
        # Drag-and-drop state
        self._drag_source: str | None = None
        self._drag_target: str | None = None

        # Callbacks to app for coordination
        self._on_histogram_opening = on_histogram_opening
        self._on_directory_opened = on_directory_opened
        self._on_selection_changed = on_selection_changed
        self._on_focus_changed = on_focus_changed

        # Session manager for save/restore behavior
        try:
            self.session_manager = SessionManager()
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                "Failed to initialize SessionManager",
                context="BrowserTab",
                exception=e
            )
            self.session_manager = None

        # Register modules
        self.module_registry.register('file_manager', RootFileManager(root_module, on_directory_opened=on_directory_opened, on_selection_changed=on_selection_changed))

        # Configure button binding if provided
        if open_file_btn:
            open_file_btn.configure(command=self.open_file_dialog)
        if close_file_btn:
            close_file_btn.configure(command=self.close_selected_file)

    def build_ui(self, parent: ttk.Frame) -> ttk.Frame:
        """Build the browser tab UI.
        
        Args:
            parent: Parent frame to build the browser in
            
        Returns:
            The browser frame containing the tree and detail panel
        """
        self.browser_frame = ttk.Frame(parent)
        
        # Use a vertical paned window so the tree gets full width and details sit below
        browser_pane = ttk.Panedwindow(self.browser_frame, orient=tk.VERTICAL)
        browser_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Tree view panel (top)
        tree_frame = ttk.Frame(browser_pane)

        self.tree = ttk.Treeview(tree_frame, columns=("class", "title"), selectmode="browse")
        self.tree.heading("#0", text="Object")
        self.tree.heading("class", text="Class")
        self.tree.heading("title", text="Title")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("class", width=130, stretch=False)
        self.tree.column("title", width=300, stretch=True)

        # Configure tags for different classes
        self.tree.tag_configure("histogram", foreground="#0066CC", font=("TkDefaultFont", 10, "bold"))
        self.tree.tag_configure("directory", foreground="#FF6600", font=("TkDefaultFont", 10, "bold"))
        self.tree.tag_configure("graph", foreground="#00AA00", font=("TkDefaultFont", 10, "bold"))
        self.tree.tag_configure("tree", foreground="#9966FF", font=("TkDefaultFont", 10))
        self.tree.tag_configure("function", foreground="#CC0000", font=("TkDefaultFont", 10))
        self.tree.tag_configure("other", foreground="#666666", font=("TkDefaultFont", 9))

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Detail panel (bottom) with scrollable area
        detail_frame = ttk.Frame(browser_pane)

        # Canvas + vertical scrollbar to allow the details area to scroll
        detail_canvas = tk.Canvas(detail_frame, highlightthickness=0)
        detail_vscroll = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=detail_canvas.yview)
        detail_canvas.configure(yscrollcommand=detail_vscroll.set)

        # The actual container where feature details will be placed
        self.detail_container = ttk.Frame(detail_canvas)
        self._detail_window = detail_canvas.create_window((0, 0), window=self.detail_container, anchor="nw")

        # Layout
        detail_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Note: details_frame setup is handled by the app when building the UI

        # Keep the canvas scrollregion updated when the inner frame changes
        def _on_detail_config(event):
            detail_canvas.configure(scrollregion=detail_canvas.bbox("all"))
        self.detail_container.bind("<Configure>", _on_detail_config)

        # Make the inner frame width always match the canvas width
        def _on_canvas_resize(event):
            try:
                detail_canvas.itemconfigure(self._detail_window, width=event.width)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to configure canvas item width",
                    context="BrowserTab.build_ui._on_canvas_resize",
                    exception=e
                )
        detail_canvas.bind("<Configure>", _on_canvas_resize)

        # Give more weight to the details (bottom) so it occupies more space
        browser_pane.add(tree_frame, weight=2)
        browser_pane.add(detail_frame, weight=3)

        # Bind events
        self.tree.bind("<<TreeviewOpen>>", self.on_open_node)
        self.tree.bind("<<TreeviewSelect>>", self.on_select_node)
        self.tree.bind("<Double-1>", self.on_double_click)
        # Drag-and-drop bindings for moving nodes
        self.tree.bind("<ButtonPress-1>", self._on_button_press)
        self.tree.bind("<B1-Motion>", self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_button_release)
        # Context menu for tree root file nodes (right-click)
        # Only provide a Close File action for now.
        self._context_menu = tk.Menu(self.browser_frame, tearoff=0)
        self._context_menu.add_command(label="Close File", command=self._context_close_file)

        # Show context menu on right-click for root file nodes only
        # (bind both Button-2 and Button-3 for macOS/other)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Button-2>", self._on_right_click)
            
        return self.browser_frame

    def open_file_dialog(self) -> None:
        """Delegate file dialog to RootFileManager via module registry."""
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.open_file_dialog(self.tree, self._populate_directory)

    def _on_right_click(self, event) -> None:
        # Identify the row under the cursor
        row = self.tree.identify_row(event.y)
        if row:
            # Only show the context menu for top-level ROOT file nodes
            try:
                parent = self.tree.parent(row)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to get parent of tree node",
                    context="BrowserTab._on_right_click",
                    exception=e
                )
                parent = None
            if parent != "":
                return

            try:
                # select the row so commands operate on the selection
                self.tree.selection_set(row)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to set tree selection",
                    context="BrowserTab._on_right_click",
                    exception=e
                )
            try:
                self._context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                try:
                    self._context_menu.grab_release()
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to release menu grab",
                        context="BrowserTab._on_right_click",
                        exception=e
                    )

    def _context_open(self) -> None:
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.handle_double_click(node_id, self.tree, on_histogram_double_clicked=self._on_histogram_double_clicked)
    
    def _context_close_file(self) -> None:
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.close_file_by_node(node_id, self.tree)

    # --- Drag and drop handlers to move nodes ---
    def _on_button_press(self, event) -> None:
        """Record drag source when left button is pressed."""
        if not self.tree:
            return
        row = self.tree.identify_row(event.y)
        self._drag_source = row if row else None
        self._drag_target = None

    def _on_drag_motion(self, event) -> None:
        """Track potential drop target while dragging (highlighting by focus)."""
        if not self.tree or not self._drag_source:
            return
        target = self.tree.identify_row(event.y)
        # Do not set target to the same as source
        if target == self._drag_source:
            target = None
        # Update visual focus to target for feedback
        try:
            if target:
                self.tree.focus(target)
            else:
                # Focus back to source while dragging over empty area
                self.tree.focus(self._drag_source)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to update tree focus during drag motion",
                context="BrowserTab._on_drag_motion",
                exception=e
            )
        self._drag_target = target

    def _on_button_release(self, event) -> None:
        """On release, attempt to move the source node under the target node."""
        if not self.tree or not self._drag_source:
            self._clear_drag_state()
            return

        drop_target = self.tree.identify_row(event.y) or ""
        # If dropping onto itself or its descendant, abort
        if drop_target == self._drag_source or self._is_descendant(drop_target, self._drag_source):
            self._clear_drag_state()
            return

        file_manager = self.module_registry.get('file_manager')
        if not file_manager:
            self._clear_drag_state()
            return

        # If drop_target is empty string, treat as top-level
        # Special-case: reordering top-level ROOT file nodes when dragging a root
        try:
            root_map = getattr(file_manager, '_root_paths_by_node', {})
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to get root map from file manager",
                context="BrowserTab._on_button_release",
                exception=e
            )
            root_map = {}

        # If both source and drop_target are root nodes, perform reorder
        if self._drag_source in root_map and drop_target in root_map:
            # Build current top-level order (exclude the source), then insert source at target index
            top_level = [rid for rid in self.tree.get_children("") if rid in root_map and rid != self._drag_source]
            try:
                insert_index = top_level.index(drop_target)
            except ValueError as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to find drop target in top-level nodes list",
                    context="BrowserTab._on_button_release",
                    exception=e
                )
                insert_index = len(top_level)
            new_order = top_level[:insert_index] + [self._drag_source] + top_level[insert_index:]
            success = file_manager.reorder_root_nodes(new_order, self.tree)
        else:
            new_parent = drop_target or ""
            success = file_manager.move_node(self._drag_source, new_parent, self.tree)
        # If the move/reorder did not succeed, silently ignore (no error popup)
        # Clear state and refresh selection
        self._clear_drag_state()

    def _is_descendant(self, node_id: str | None, ancestor_id: str | None) -> bool:
        """Return True if `node_id` is a descendant of `ancestor_id` in the tree."""
        if not node_id or not ancestor_id:
            return False
        try:
            current = node_id
            while current:
                parent = self.tree.parent(current)
                if parent == ancestor_id:
                    return True
                current = parent
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to check node ancestry in tree",
                context="BrowserTab._is_descendant",
                exception=e
            )
            return False
        return False

    def _clear_drag_state(self) -> None:
        self._drag_source = None
        self._drag_target = None

    def _populate_directory(self, parent_id: str, directory) -> None:
        """Delegate directory population to RootFileManager."""
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.populate_directory(parent_id, directory, self.tree, file_manager.get_tag_for_class)

    def close_selected_file(self) -> None:
        """Close the currently selected file (root node) in the tree."""
        if not self.tree:
            return
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.close_file_by_node(node_id, self.tree)

    def on_open_node(self, event) -> None:
        """Handle tree node expansion (delegated to file manager)."""
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.handle_open_node(node_id, self.tree, self._populate_directory)

    def on_select_node(self, event) -> None:
        """Handle tree node selection (delegated to file manager)."""
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.handle_select_node(node_id, self.tree)

    def on_double_click(self, event) -> None:
        """Handle tree node double-click (delegated to file manager)."""
        node_id = self.tree.focus()
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.handle_double_click(node_id, self.tree, on_histogram_double_clicked=self._on_histogram_double_clicked)

    def _on_histogram_double_clicked(self, obj, root_path: str, path: str) -> None:
        """Callback when a histogram object is double-clicked in the tree.
        
        Delegates to the app via callback.
        
        Args:
            obj: The ROOT histogram object
            root_path: Path to the ROOT file
            path: Path within the ROOT file to the histogram
        """
        try:
            if self._on_histogram_opening and callable(self._on_histogram_opening):
                self._on_histogram_opening(obj, root_path, path)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.ERROR,
                "Failed to open histogram from double-click",
                context="BrowserTab._on_histogram_double_clicked",
                exception=e
            )

    def focus(self) -> None:
        """Set focus to the browser - show browser and hide histograms."""
        # Notify app of focus change
        if self._on_focus_changed and callable(self._on_focus_changed):
            try:
                self._on_focus_changed(True)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.WARNING,
                    "Failed to notify app of browser focus",
                    context="BrowserTab.focus",
                    exception=e
                )
        
        # Show and focus browser
        self.show()
        if self.tree:
            try:
                self.tree.focus_set()
            except tk.TclError as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to set focus to tree widget",
                    context="BrowserTab.focus",
                    exception=e
                )

    def show(self) -> None:
        """Show the browser frame."""
        if self.browser_frame and not self.browser_frame.winfo_ismapped():
            self.browser_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    def hide(self) -> None:
        """Hide the browser frame."""
        if self.browser_frame and self.browser_frame.winfo_ismapped():
            self.browser_frame.pack_forget()

    def cleanup(self) -> None:
        """Clean up resources (delegated to file manager)."""
        file_manager = self.module_registry.get('file_manager')
        if file_manager:
            file_manager.cleanup()

    def apply_autosave(self) -> None:
        """Load and apply the most recent autosave session state."""
        try:
            if not self.session_manager:
                return
            data = self.session_manager.load_latest_autosave()
            if not data:
                return
            file_manager = self.module_registry.get('file_manager')
            self.session_manager.apply_tree_state(data, self.tree, file_manager=file_manager)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to apply autosaved session state",
                context="BrowserTab.apply_autosave",
                exception=e
            )

    def save_session_on_restart(self) -> None:
        """Save current session state before restart."""
        try:
            if not self.session_manager:
                return
            open_files = list(self._open_root_files.keys())
            if open_files:
                self.session_manager.save_last_files(open_files)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to save session on restart",
                context="BrowserTab.save_session_on_restart",
                exception=e
            )

    def auto_save_session(self, hist_name: str = "app", hist_path: str = "") -> None:
        """Auto-save session on application close.
        
        Args:
            hist_name: Name of the current histogram (if any)
            hist_path: Path to the current histogram (if any)
        """
        try:
            if not self.session_manager:
                return
            
            file_manager = self.module_registry.get('file_manager')
            self.session_manager.auto_save_session(
                hist_name, hist_path, {}, [], 
                tree=self.tree, 
                file_manager=file_manager
            )
        except Exception:
            pass
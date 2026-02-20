from features.root_directory import RootDirectoryFeature
from features.feature_registry import FeatureRegistry

class RootFileManager:
    """
    RootFileManager
    ----------------
    Unified module for ROOT file operations in the browser tab.

    Responsibilities:
    - File dialog for selecting ROOT files
    - Opening ROOT files and managing open file state
    - Browsing ROOT file contents (tree view, object/class/title display)
    - Provides interface for tab to populate directory contents

    Usage:
    - Call open_file_dialog(callback) to prompt user for files and handle result
    - Call open_path(path, tree, populate_directory_callback) to open and display a file
    - Maintains open file state and node mapping for tree navigation
    """
    def __init__(self, ROOT, on_directory_opened=None, on_selection_changed=None):
        """
        Initialize RootFileManager.
        
        Args:
            ROOT: PyROOT module reference
            on_directory_opened: Callback(directory, path) when directory is opened
            on_selection_changed: Callback(obj, path) when selection changes
        """
        self.ROOT = ROOT
        self._open_root_files = {}
        self._root_paths_by_node = {}
        self.root_file = None
        
        # Callbacks to app for notifications
        self._on_directory_opened = on_directory_opened
        self._on_selection_changed = on_selection_changed
        
        # Feature registry and features (keep local mapping but also register
        # with the application's FeatureRegistry so selection events are
        # delivered to features)
        self.feature_registry = {}
        root_dir_feature = RootDirectoryFeature(ROOT)
        self.feature_registry['root_directory'] = root_dir_feature

        try:
            # Register with app's FeatureRegistry if available
            # This is set via register_feature_registry() after initialization
            pass
        except Exception:
            # Non-fatal: continue without central registry
            pass
    # Public API: file dialogs and file opening
    def open_file_dialog(self, tree, populate_directory_callback):
        """
        Open file dialog to select ROOT files.
        For each selected path, open the file and populate the tree via
        `open_path`, which will invoke `populate_directory_callback`.
        """
        from tkinter import filedialog
        import os
        default_dir = os.path.join(os.getcwd(), "data")
        if not os.path.isdir(default_dir):
            default_dir = os.getcwd()
        paths = filedialog.askopenfilenames(
            title="Open ROOT file",
            initialdir=default_dir,
            filetypes=[("ROOT files", "*.root"), ("All files", "*")],
        )
        if paths:
            for path in paths:
                # open_path will insert the root node and call populate_directory_callback
                self.open_path(path, tree, populate_directory_callback)

    def open_path(self, path, tree, populate_directory_callback):
        """
        Open a ROOT file and populate the tree view.
        - path: file path to open
        - tree: ttk.Treeview instance
        - populate_directory_callback: function to call for directory population
        """
        import os
        path = os.path.abspath(path)
        if path in self._open_root_files:
            root_file = self._open_root_files[path]
            root_id = self._node_for_root_path(path)
            if root_id:
                tree.selection_set(root_id)
                tree.focus(root_id)
                tree.see(root_id)
            self.root_file = root_file
            return
        root_file = self.ROOT.TFile.Open(path)
        if not root_file or root_file.IsZombie():
            return None
        self.root_file = root_file
        self._open_root_files[path] = root_file
        root_id = tree.insert("", "end", text=os.path.basename(path), values=("TFile", ""))
        tree.set(root_id, "class", "TFile")
        tree.set(root_id, "title", root_file.GetTitle() or path)
        self._root_paths_by_node[root_id] = path
        tree.item(root_id, open=True)
        populate_directory_callback(root_id, root_file)
        return root_file

    def populate_directory(self, parent_id, directory, tree, get_tag_for_class):
        """Delegate directory population to RootDirectoryFeature."""
        feature = self.feature_registry.get('root_directory')
        if feature:
            feature.populate_directory(parent_id, directory, tree, get_tag_for_class)

    def show_details(self, parent, obj, path):
        """Delegate details UI to RootDirectoryFeature."""
        feature = self.feature_registry.get('root_directory')
        if feature:
            feature.show_details(parent, obj, path)

    def get_tag_for_class(self, class_name: str) -> str:
        """Return the appropriate tag for a ROOT class name."""
        if class_name.startswith("TH"):
            return "histogram"
        elif class_name in ("TDirectory", "TDirectoryFile"):
            return "directory"
        elif class_name.startswith("TGraph"):
            return "graph"
        elif class_name.startswith("TTree"):
            return "tree"
        elif class_name.startswith("TF"):
            return "function"
        else:
            return "other"

    def populate_directory(self, parent_id, directory, tree, get_tag_for_class):
        """Delegate directory population to RootDirectoryFeature."""
        feature = self.feature_registry.get('root_directory')
        if feature:
            feature.populate_directory(parent_id, directory, tree, get_tag_for_class)

    def handle_open_node(self, node_id, tree, populate_directory_callback):
        """Handle tree node expansion.
        
        Args:
            node_id: The node ID being expanded
            tree: The tree view widget
            populate_directory_callback: Callback to populate directory contents
        """
        root_file, _ = self._root_context_for_node(node_id, tree)
        if not node_id or root_file is None:
            return
        path = self._node_path(node_id, tree)
        if path is None:
            return
        directory = root_file.Get(path)
        if not directory:
            return
        if isinstance(directory, self.ROOT.TDirectory):
            populate_directory_callback(node_id, directory)
            if self._on_directory_opened and callable(self._on_directory_opened):
                try:
                    self._on_directory_opened(directory, path)
                except Exception:
                    pass

    def handle_select_node(self, node_id, tree):
        """Handle tree node selection.
        
        Args:
            node_id: The node ID being selected
            tree: The tree view widget
        """
        root_file, root_path = self._root_context_for_node(node_id, tree)
        if not node_id or root_file is None:
            return
        self.root_file = root_file
        path = self._node_path(node_id, tree)
        if path is None:
            return
        # If the root node itself was selected, treat the object as the TFile
        if path == "":
            obj = root_file
        else:
            obj = root_file.Get(path)
        if not obj:
            if self._on_selection_changed and callable(self._on_selection_changed):
                try:
                    self._on_selection_changed(None, path)
                except Exception:
                    pass
            return
        if self._on_selection_changed and callable(self._on_selection_changed):
            try:
                self._on_selection_changed(obj, path)
            except Exception:
                pass

    def handle_double_click(self, node_id, tree, on_histogram_double_clicked=None):
        """Handle tree node double-click to open histograms.
        
        Args:
            node_id: The tree node ID that was double-clicked
            tree: The tree view widget
            on_histogram_double_clicked: Callback function(obj, root_path, path) for histogram objects
        """
        root_file, _ = self._root_context_for_node(node_id, tree)
        if not node_id or root_file is None:
            return
        path = self._node_path(node_id, tree)
        if path is None:
            return
        obj = root_file.Get(path)
        if not obj:
            return
        if obj.ClassName().startswith("TH"):
            root_path = root_file.GetName()
            if on_histogram_double_clicked and callable(on_histogram_double_clicked):
                on_histogram_double_clicked(obj, root_path, path)

    def cleanup(self):
        """Clean up resources."""
        for root_file in self._open_root_files.values():
            try:
                root_file.Close()
            except Exception:
                pass
        self._open_root_files.clear()
        self._root_paths_by_node.clear()

    def close_file_by_path(self, path: str, tree=None) -> bool:
        """Close an opened ROOT file by filesystem path and remove its tree node.

        Returns True if a file was closed, False otherwise.
        """
        import os
        path = os.path.abspath(path)
        root_id = self._node_for_root_path(path)
        if not root_id:
            return False
        # Close and remove from open files
        root_file = self._open_root_files.pop(path, None)
        try:
            if root_file:
                root_file.Close()
        except Exception:
            pass
        # Remove node mapping
        try:
            self._root_paths_by_node.pop(root_id, None)
        except Exception:
            pass
        # Remove node from tree if provided
        if tree is not None:
            try:
                tree.delete(root_id)
            except Exception:
                pass
        return True

    def close_file_by_node(self, node_id: str, tree) -> bool:
        """Close the ROOT file owning the given tree node.

        Finds the root node for the provided node_id and closes that file.
        """
        if not node_id:
            return False
        root_id = self._root_node_for(node_id, tree)
        if not root_id:
            return False
        path = self._root_paths_by_node.get(root_id)
        if not path:
            return False
        return self.close_file_by_path(path, tree)

    def move_node(self, node_id: str, new_parent_id: str, tree) -> bool:
        """Move a tree node to a new parent.

        Safety rules:
        - Root file nodes (those in `_root_paths_by_node`) may only be moved among
          the top-level (i.e., `new_parent_id == ""`). Moving a root file under
          another node is not allowed.
        - Non-root nodes may be reparented freely; this method will call
          `tree.move(node_id, new_parent_id, 'end')` and return True on success.

        Returns True if the move succeeded, False otherwise.
        """
        if not node_id:
            return False
        # If node is a registered root file, disallow non-root parenting
        if node_id in self._root_paths_by_node:
            if new_parent_id != "":
                return False
            try:
                # Move among top-level positions
                tree.move(node_id, "", "end")
                return True
            except Exception:
                return False

        # For non-root nodes, allow reparenting
        try:
            tree.move(node_id, new_parent_id or "", "end")
            return True
        except Exception:
            return False

    def reorder_root_nodes(self, ordered_root_ids: list[str], tree) -> bool:
        """Reorder top-level root nodes to match `ordered_root_ids`.

        `ordered_root_ids` should be a list of node IDs (strings) representing
        the desired order of the top-level roots. Any IDs not present at the
        top-level are ignored. Returns True on success.
        """
        if not ordered_root_ids:
            return False
        try:
            # Place each provided root id at the requested index
            idx = 0
            for rid in ordered_root_ids:
                if rid in self._root_paths_by_node:
                    tree.move(rid, "", idx)
                    idx += 1
            return True
        except Exception:
            return False

    # Helper methods for node context
    def _node_path(self, node_id, tree):
        if not node_id:
            return None
        parts = []
        current = node_id
        while current:
            parent = tree.parent(current)
            name = tree.item(current, "text")
            if parent == "" and current in self._root_paths_by_node:
                pass
            elif name != "/" and name != "":
                parts.append(name)
            current = parent
        if not parts:
            return ""
        return "/".join(reversed(parts))

    def _root_context_for_node(self, node_id, tree):
        root_id = self._root_node_for(node_id, tree)
        if not root_id:
            return None, None
        root_path = self._root_paths_by_node.get(root_id)
        if not root_path:
            return None, None
        return self._open_root_files.get(root_path), root_path

    def _root_node_for(self, node_id, tree):
        current = node_id
        while current:
            parent = tree.parent(current)
            if parent == "":
                return current
            current = parent
        return None

    def _node_for_root_path(self, path):
        """
        Get the tree node ID for a ROOT file path.
        """
        for node_id, node_path in self._root_paths_by_node.items():
            if node_path == path:
                return node_id
        return None

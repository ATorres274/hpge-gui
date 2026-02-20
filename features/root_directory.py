from tkinter import ttk

from .feature import Feature


class RootDirectoryFeature(Feature):
    """Feature for handling ROOT directory events and population."""
    name = "Root Directory"

    def __init__(self, ROOT, app=None):
        super().__init__()
        self.app = app
        self.ROOT = ROOT

    def show_details(self, parent: ttk.Frame, obj, path: str):
        import tkinter as tk
        from tkinter import ttk

        # Clear any existing contents so only one details panel is shown
        for child in parent.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        # Header
        ttk.Label(parent, text="Details", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(6, 0))

        # Simpler scrollable text area to reliably present object details
        text_frame = ttk.Frame(parent)
        text_widget = tk.Text(text_frame, wrap=tk.WORD)
        vscroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=vscroll.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        def _write(line: str = ""):
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, line + "\n")
            text_widget.config(state=tk.DISABLED)

        if obj is None:
            _write(f"Missing object: {path}")
            return
        try:
            class_name = obj.ClassName()
        except Exception:
            class_name = str(type(obj))

        # If the object exposes a list of keys (TFile / TDirectory), list all contained objects
        if hasattr(obj, "GetListOfKeys"):
            _write(f"File: {path or obj.GetName()}")
            keys = []
            try:
                keys = obj.GetListOfKeys()
            except Exception:
                keys = []
            if not keys:
                _write("(no objects)")
                return
            _write("")
            _write("Objects:")
            for key in keys:
                try:
                    name = key.GetName()
                    cls = key.GetClassName()
                    title = key.GetTitle() or ""
                    _write(f" - {name}  ({cls})  {title}")
                except Exception:
                    continue
            return

        # Otherwise render single-object details
        _write(f"Path: {path}")
        _write(f"Class: {class_name}")

        if hasattr(obj, "GetName"):
            try:
                _write(f"Name: {obj.GetName()}")
            except Exception:
                pass
        if hasattr(obj, "GetTitle"):
            try:
                _write(f"Title: {obj.GetTitle()}")
            except Exception:
                pass
        if hasattr(obj, "GetEntries"):
            try:
                _write(f"Entries: {obj.GetEntries()}")
            except Exception:
                pass
        if hasattr(obj, "GetVal"):
            try:
                _write(f"Value: {obj.GetVal()}")
            except Exception:
                pass
        
    def on_file_opened(self, app, root_file) -> None:
        # No-op by default; feature can react to file opened if needed
        pass

    def on_selection(self, app, obj, path: str) -> None:
        # When a selection occurs, if the app provides a details frame, show details
        details_parent = getattr(app, 'details_frame', None)
        if details_parent is not None:
            # Clear and show details in the provided parent
            self.show_details(details_parent, obj, path)

    def on_directory_opened(self, app, directory, path: str) -> None:
        # No-op by default; could be used to trigger UI updates
        pass
        
    def populate_directory(self, parent_id, directory, tree, get_tag_for_class):
        tree.delete(*tree.get_children(parent_id))
        keys = directory.GetListOfKeys()
        if not keys:
            return
        for key in keys:
            name = key.GetName()
            class_name = key.GetClassName()
            obj_title = key.GetTitle() or ""
            tag = get_tag_for_class(class_name)
            node_id = tree.insert(parent_id, "end", text=name, values=(class_name, obj_title), tags=(tag,))
            if class_name in ("TDirectory", "TDirectoryFile"):
                tree.insert(node_id, "end", text="(loading)")

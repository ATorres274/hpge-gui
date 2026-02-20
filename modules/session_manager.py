"""Session management for saving and restoring workspace state."""

from __future__ import annotations

import json
import os
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Any

from .error_dispatcher import get_dispatcher, ErrorLevel


class SessionManager:
    """Manage save/restore of workspace state including fits and parameters."""

    def __init__(self) -> None:
        self.session_dir = os.path.join(os.path.expanduser("~"), ".pyhpge_gui", "sessions")
        self._dispatcher = get_dispatcher()
        try:
            os.makedirs(self.session_dir, exist_ok=True)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.WARNING,
                f"Failed to create session directory: {e}",
                context="SessionManager",
                exception=e
            )

    def save_session(
        self,
        histogram_name: str,
        histogram_path: str,
        fit_states: dict[int, dict],
        peaks: list[dict] | None = None,
        filepath: str | None = None,
        tree: any | None = None,
        file_manager: any | None = None,
        silent: bool = False,
    ) -> str | None:
        """
        Save current workspace session to file.

        Args:
            histogram_name: Name of the histogram
            histogram_path: Path within ROOT file to histogram
            fit_states: Dictionary of fit states
            peaks: Optional list of detected peaks
            filepath: Optional output path

        Returns:
            Path to saved session file or None if cancelled
        """
        if filepath is None:
            default_name = f"{histogram_name}_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = self._prompt_save_filename(default_name)

        if not filepath:
            return None

        try:
            session_data = {
                "version": "1.0",
                "saved_at": datetime.now().isoformat(),
                "histogram": {
                    "name": histogram_name,
                    "path": histogram_path,
                },
                "peaks": peaks or [],
                "fits": self._serialize_fit_states(fit_states),
            }

            # If a tree and optional file_manager are provided, capture tree state
            if tree is not None:
                try:
                    root_map = getattr(file_manager, "_root_paths_by_node", {}) if file_manager is not None else {}

                    def _node_text_path(node_id: str) -> str:
                        # Build a slash-separated path from node text labels
                        parts = []
                        current = node_id
                        try:
                            while current:
                                parent = tree.parent(current)
                                name = tree.item(current, "text")
                                if parent == "" and current in root_map:
                                    # For root nodes, prefer filesystem path when available
                                    return f"TFILE:{root_map.get(current)}"
                                elif name != "/" and name != "":
                                    parts.append(name)
                                current = parent
                        except Exception:
                            return tree.item(node_id, "text")
                        if not parts:
                            return ""
                        return "/".join(reversed(parts))

                    # Collect open nodes recursively
                    open_nodes = []

                    def _collect_open(nid: str):
                        try:
                            if tree.item(nid, "open"):
                                open_nodes.append(_node_text_path(nid))
                        except Exception as e:
                            self._dispatcher.emit(
                                ErrorLevel.INFO,
                                "Failed to check if tree node is open",
                                context="SessionManager.apply_tree_state._collect_open",
                                exception=e
                            )
                        try:
                            for c in tree.get_children(nid):
                                _collect_open(c)
                        except Exception as e:
                            self._dispatcher.emit(
                                ErrorLevel.INFO,
                                "Failed to get tree node children during collection",
                                context="SessionManager.apply_tree_state._collect_open",
                                exception=e
                            )

                    for top in tree.get_children(""):
                        _collect_open(top)

                    # Selected nodes
                    selected = []
                    try:
                        for s in tree.selection():
                            selected.append(_node_text_path(s))
                    except Exception as e:
                        self._dispatcher.emit(
                            ErrorLevel.INFO,
                            "Failed to get tree selection",
                            context="SessionManager.apply_tree_state",
                            exception=e
                        )
                        selected = []

                    # Root ordering (prefer filesystem paths when available)
                    root_order = []
                    try:
                        for rid in tree.get_children(""):
                            if rid in root_map:
                                root_order.append(root_map.get(rid))
                            else:
                                root_order.append(tree.item(rid, "text"))
                    except Exception as e:
                        self._dispatcher.emit(
                            ErrorLevel.INFO,
                            "Failed to collect root node ordering",
                            context="SessionManager.apply_tree_state",
                            exception=e
                        )
                        root_order = []

                    session_data["tree_state"] = {
                        "open_nodes": open_nodes,
                        "selected": selected,
                        "root_order": root_order,
                    }
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.WARNING,
                        "Failed to capture tree state",
                        context="SessionManager.save_session",
                        exception=e
                    )

            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            if not silent:
                self._safe_showinfo("Session saved", f"Session saved to:\n{filepath}")
            return filepath

        except Exception as e:
            if not silent:
                self._safe_showerror("Save failed", f"Failed to save session:\n{e}")
            return None

    def _serialize_fit_states(self, fit_states: dict[int, dict]) -> list[dict]:
        """
        Serialize fit states to JSON-compatible format.

        Args:
            fit_states: Dictionary of fit states

        Returns:
            List of serialized fit data
        """
        serialized_fits = []

        for tab_id, fit_state in sorted(fit_states.items()):
            fit_data = {
                "tab_id": tab_id,
                "fit_function": self._get_var_value(fit_state.get("fit_func_var")),
                "energy_keV": self._get_var_value(fit_state.get("energy_var")),
                "width_keV": self._get_var_value(fit_state.get("width_var")),
                "peak_idx": fit_state.get("peak_idx"),
            }

            # Serialize parameters
            param_entries = fit_state.get("param_entries", [])
            param_fixed = fit_state.get("param_fixed_vars", [])

            fit_data["parameters"] = [
                {
                    "value": self._get_var_value(param_var),
                    "fixed": self._get_var_value(param_fixed[i]) if i < len(param_fixed) else False,
                }
                for i, param_var in enumerate(param_entries)
            ]

            # Include cached results if available
            cached_results = fit_state.get("cached_results")
            if cached_results:
                fit_data["cached_results"] = cached_results

            serialized_fits.append(fit_data)

        return serialized_fits

    def _get_var_value(self, var) -> Any:
        """Get value from Tkinter variable safely."""
        if var is None:
            return None
        if hasattr(var, "get"):
            return var.get()
        return var

    def _safe_showinfo(self, title: str, message: str) -> None:
        """Show info messagebox safely (no-op if GUI unavailable)."""
        try:
            messagebox.showinfo(title, message)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to show info messagebox",
                context="SessionManager._safe_showinfo",
                exception=e
            )

    def _safe_showerror(self, title: str, message: str) -> None:
        """Show error messagebox safely (no-op if GUI unavailable)."""
        try:
            messagebox.showerror(title, message)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to show error messagebox",
                context="SessionManager._safe_showerror",
                exception=e
            )

    def _prompt_save_filename(self, default_name: str) -> str | None:
        """Prompt user for a save filename; returns None if cancelled or unavailable."""
        try:
            return filedialog.asksaveasfilename(
                title="Save Session",
                initialdir=self.session_dir,
                initialfile=default_name,
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to show save filename dialog",
                context="SessionManager._prompt_save_filename",
                exception=e
            )
            return None

    def _prompt_open_filename(self) -> str | None:
        """Prompt user to choose a session file to open; returns None if cancelled."""
        try:
            return filedialog.askopenfilename(
                title="Load Session",
                initialdir=self.session_dir,
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
        except Exception:
            return None

    def apply_tree_state(self, session_data: dict, tree, file_manager=None) -> bool:
        """Apply saved tree state to a live `ttk.Treeview`.

        This is best-effort: it will try to open root files via `file_manager.open_path`
        when needed, reorder top-level roots using `file_manager.reorder_root_nodes`,
        expand saved open nodes, and restore selection.
        Returns True if any action was performed, False otherwise.
        """
        if not session_data or tree is None:
            return False

        tree_state = session_data.get("tree_state") or {}
        if not tree_state:
            return False

        root_map = getattr(file_manager, "_root_paths_by_node", {}) if file_manager is not None else {}

        def _find_node_by_text_path(text_path: str) -> str | None:
            # Empty path -> root node
            if text_path is None:
                return None
            if text_path.startswith("TFILE:"):
                fp = text_path[len("TFILE:") :]
                # find node id for this file path
                for nid, p in getattr(file_manager, "_root_paths_by_node", {}).items():
                    if p == fp:
                        return nid
                return None

            if text_path == "":
                return None
            parts = [p for p in text_path.split("/") if p]
            # search all top-level nodes
            try:
                for top in tree.get_children(""):
                    # try matching starting at this top node
                    def _walk(idx: int, nid: str) -> str | None:
                        if idx >= len(parts):
                            return nid
                        for c in tree.get_children(nid):
                            try:
                                if tree.item(c, "text") == parts[idx]:
                                    res = _walk(idx + 1, c)
                                    if res:
                                        return res
                            except Exception as e:
                                self._dispatcher.emit(
                                    ErrorLevel.INFO,
                                    "Failed to check tree node during walk",
                                    context="SessionManager.apply_tree_state._walk",
                                    exception=e
                                )
                                continue
                        return None

                    # check top node text first
                    try:
                        if tree.item(top, "text") == parts[0]:
                            found = _walk(1, top)
                            if found:
                                return found
                    except Exception as e:
                        self._dispatcher.emit(
                            ErrorLevel.INFO,
                            "Failed to check top node during tree search",
                            context="SessionManager.apply_tree_state",
                            exception=e
                        )
                        continue
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to search for node by text path",
                    context="SessionManager.apply_tree_state._find_node_by_text_path",
                    exception=e
                )
                return None
            return None

        acted = False

        # 1) Reopen missing root files and reorder top-level if provided
        root_order = tree_state.get("root_order", []) or []
        if root_order and file_manager is not None:
            node_order = []
            for path in root_order:
                if isinstance(path, str) and path.startswith("TFILE:"):
                    fp = path[len("TFILE:") :]
                else:
                    fp = path
                # attempt to find existing node id
                nid = None
                for id_, p in getattr(file_manager, "_root_paths_by_node", {}).items():
                    if p == fp:
                        nid = id_
                        break
                # if not open but file exists, try to open it
                try:
                    if nid is None and fp and os.path.isfile(fp):
                        # open_path will insert node and populate directory
                        try:
                            file_manager.open_path(fp, tree, lambda rid, rf: file_manager.populate_directory(rid, rf, tree, file_manager.get_tag_for_class))
                        except Exception as e:
                            self._dispatcher.emit(
                                ErrorLevel.INFO,
                                f"Failed to reopen file during tree restoration: {fp}",
                                context="SessionManager.apply_tree_state",
                                exception=e
                            )
                        nid = file_manager._node_for_root_path(fp)
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to process root file during tree state restoration",
                        context="SessionManager.apply_tree_state",
                        exception=e
                    )
                    nid = None

                if nid:
                    node_order.append(nid)

            if node_order:
                try:
                    file_manager.reorder_root_nodes(node_order, tree)
                    acted = True
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to reorder root nodes during tree restoration",
                        context="SessionManager.apply_tree_state",
                        exception=e
                    )

        # 2) Expand open nodes
        open_nodes = tree_state.get("open_nodes", []) or []
        # Collapse all nodes first so saved expanded state is applied precisely
        try:
            def _collapse_all(nid: str) -> None:
                try:
                    tree.item(nid, open=False)
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to collapse tree node",
                        context="SessionManager.apply_tree_state._collapse_all",
                        exception=e
                    )
                try:
                    for c in tree.get_children(nid):
                        _collapse_all(c)
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to get children during tree collapse",
                        context="SessionManager.apply_tree_state._collapse_all",
                        exception=e
                    )

            for top in tree.get_children(""):
                _collapse_all(top)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to collapse all tree nodes",
                context="SessionManager.apply_tree_state",
                exception=e
            )

        for txt in open_nodes:
            nid = _find_node_by_text_path(txt)
            if nid:
                try:
                    # ensure all parents open (so the node becomes visible)
                    parent_stack = []
                    parent = tree.parent(nid)
                    while parent:
                        parent_stack.append(parent)
                        parent = tree.parent(parent)
                    for p in reversed(parent_stack):
                        try:
                            tree.item(p, open=True)
                        except Exception as e:
                            self._dispatcher.emit(
                                ErrorLevel.INFO,
                                "Failed to open parent node during tree restoration",
                                context="SessionManager.apply_tree_state",
                                exception=e
                            )
                    try:
                        tree.item(nid, open=True)
                    except Exception as e:
                        self._dispatcher.emit(
                            ErrorLevel.INFO,
                            "Failed to open node during tree restoration",
                            context="SessionManager.apply_tree_state",
                            exception=e
                        )
                    acted = True
                except Exception as e:
                    self._dispatcher.emit(
                        ErrorLevel.INFO,
                        "Failed to restore open state for tree node",
                        context="SessionManager.apply_tree_state",
                        exception=e
                    )
                    continue

        # 3) Restore selection (prefer first valid selection)
        selected = tree_state.get("selected", []) or []
        sel_ids = []
        for txt in selected:
            nid = _find_node_by_text_path(txt)
            if nid:
                sel_ids.append(nid)
        if sel_ids:
            try:
                tree.selection_set(sel_ids)
                tree.see(sel_ids[0])
                acted = True
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to restore tree selection",
                    context="SessionManager.apply_tree_state",
                    exception=e
                )

        return acted

    def load_session(self, filepath: str | None = None, tree=None, file_manager=None) -> dict[str, Any] | None:
        """
        Load workspace session from file and optionally apply tree state.

        If `tree` and `file_manager` are provided, `tree_state` in the session
        will be applied to the live tree.
        """
        if filepath is None:
            filepath = self._prompt_open_filename()

        if not filepath or not os.path.isfile(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            # Validate session structure
            if "version" not in session_data or "histogram" not in session_data:
                self._safe_showerror("Invalid session", "Session file is not valid")
                return None

            # Optionally apply tree state
            try:
                if tree is not None:
                    self.apply_tree_state(session_data, tree, file_manager=file_manager)
            except Exception as e:
                self._dispatcher.emit(
                    ErrorLevel.INFO,
                    "Failed to apply saved tree state",
                    context="SessionManager.load_session",
                    exception=e
                )

            self._safe_showinfo("Session loaded", f"Loaded session from:\n{filepath}")
            return session_data

        except Exception as e:
            self._safe_showerror("Load failed", f"Failed to load session:\n{e}")
            return None

    def auto_save_session(
        self,
        histogram_name: str,
        histogram_path: str,
        fit_states: dict[int, dict],
        peaks: list[dict] | None = None,
        tree: any | None = None,
        file_manager: any | None = None,
    ) -> str | None:
        """
        Auto-save session without prompting user.

        Args:
            histogram_name: Name of the histogram
            histogram_path: Path within ROOT file to histogram
            fit_states: Dictionary of fit states
            peaks: Optional list of detected peaks

        Returns:
            Path to saved session file or None if failed
        """
        try:
            # Create auto-save directory
            autosave_dir = os.path.join(self.session_dir, "autosave")
            os.makedirs(autosave_dir, exist_ok=True)

            # Use sanitized histogram name for filename
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in histogram_name)
            filename = f"{safe_name}_autosave.json"
            filepath = os.path.join(autosave_dir, filename)

            return self.save_session(
                histogram_name,
                histogram_path,
                fit_states,
                peaks,
                filepath=filepath,
                tree=tree,
                file_manager=file_manager,
                silent=True,
            )

        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to auto-save session",
                context="SessionManager.auto_save_session",
                exception=e
            )
            return None

    def load_latest_autosave(self) -> dict[str, Any] | None:
        """Return the most-recent autosave JSON payload from the autosave directory.

        This is a convenience helper used by the application startup to retrieve
        whatever the latest autosave file is, without the caller needing to read
        or parse JSON themselves.
        """
        try:
            autosave_dir = os.path.join(self.session_dir, "autosave")
            if not os.path.isdir(autosave_dir):
                return None
            candidates = [os.path.join(autosave_dir, f) for f in os.listdir(autosave_dir) if f.endswith('.json')]
            if not candidates:
                return None
            latest = max(candidates, key=os.path.getmtime)
            with open(latest, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to load latest autosave",
                context="SessionManager.load_latest_autosave",
                exception=e
            )
            return None

    def save_last_files(self, paths: list[str]) -> str | None:
        """
        Save a small session file listing the last opened file paths.

        This writes to ~/.pyhpge_gui/session.json and is used by the
        application restart flow to remember which files to reopen.
        """
        try:
            session_path = os.path.join(os.path.expanduser("~"), ".pyhpge_gui")
            os.makedirs(session_path, exist_ok=True)
            file_path = os.path.join(session_path, "session.json")
            payload = {
                "last_files": [os.path.abspath(os.path.expanduser(p)) for p in paths],
                "saved_at": datetime.now().isoformat(),
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            return file_path
        except Exception as e:
            self._dispatcher.emit(
                ErrorLevel.INFO,
                "Failed to save last opened files list",
                context="SessionManager.save_last_files",
                exception=e
            )
            return None

#!/usr/bin/env python3
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(__file__)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gui_base.app_shell import RootBrowserApp


def _get_session_file_path() -> str:
    """Get the session file path."""
    return os.path.join(os.path.expanduser("~"), ".pyhpge_gui", "session.json")


def _load_last_session_paths() -> list[str]:
    """Load last session file paths."""
    try:
        session_path = _get_session_file_path()
        if not os.path.isfile(session_path):
            return []
        
        with open(session_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        
        last_files = data.get("last_files")
        if isinstance(last_files, list):
            resolved = []
            for path in last_files:
                resolved_path = os.path.abspath(os.path.expanduser(path))
                if os.path.isfile(resolved_path):
                    resolved.append(resolved_path)
            return resolved
        
        last_file = data.get("last_file")
        if last_file:
            resolved_path = os.path.abspath(os.path.expanduser(last_file))
            if os.path.isfile(resolved_path):
                return [resolved_path]
    except Exception:
        return []
    return []


def _resolve_initial_paths(arg_path: str | None, use_last: bool) -> list[str] | None:
    """Resolve initial paths from command-line arguments.
    
    Args:
        arg_path: Optional path provided as command-line argument
        use_last: Whether to load last session (--last flag)
    
    Returns:
        List of paths to open, or None if no paths should be opened
    """
    if arg_path and os.path.isfile(arg_path):
        return [os.path.abspath(arg_path)]
    if use_last:
        paths = _load_last_session_paths()
        return paths or None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("path", nargs="?")
    parser.add_argument("--last", action="store_true")
    args, _ = parser.parse_known_args()

    initial_paths = _resolve_initial_paths(args.path, args.last)
    app = RootBrowserApp(initial_paths=initial_paths)
    app.mainloop()


if __name__ == "__main__":
    main()

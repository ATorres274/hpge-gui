# AGENTS.md — Instructions for AI Coding Agents

This file documents conventions, architecture, and workflow rules that any AI
coding agent working in this repository should follow.

---

## Project Overview

**HPGe GUI** is a PyROOT-based desktop application for browsing and analyzing
High-Purity Germanium (HPGe) detector spectra stored in ROOT files.  The UI is
built with Tkinter and follows a strict **Tab → Module → Feature** architecture.

```
gui_base/app_shell.py      ← top-level Tk window, visibility orchestration
tab_managers/              ← lightweight UI managers (browser, histogram, batch)
modules/                   ← domain logic, file I/O, session management
features/                  ← pure action handlers; no UI or persistent state
tests/                     ← pytest test suite (see Running Tests below)
```

---

## Architecture Rules

| Layer | Owns | Must NOT |
|---|---|---|
| App (app_shell) | Top bar UI, tab init, visibility routing | Contain domain logic |
| Tab managers | UI layout, module wiring | Talk to other tabs directly |
| Modules | Domain logic, file ops, session state | Import tkinter widgets |
| Features | Pure computation / action handlers | Hold state or call UI code |

Communication is **one-directional**: App → Tab → Module → Feature.  Callbacks
are the only allowed reverse path (tab notifies app via a callback supplied at
construction time).

---

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Entry point; parses `--last` flag; calls `_resolve_initial_paths` |
| `gui_base/app_shell.py` | `RootBrowserApp` — main Tk window |
| `tab_managers/browser_tab.py` | File browser tree view; delegates to `RootFileManager` |
| `tab_managers/histogram_tab.py` | Histogram preview area; `HistogramPreviewRenderer` per tab |
| `modules/root_file_manager.py` | Opens ROOT files, manages `_open_root_files` dict |
| `modules/session_manager.py` | Saves/loads session JSON; autosave; `save_last_files` |
| `modules/error_dispatcher.py` | Singleton `ErrorDispatcher`; use `get_dispatcher()` |
| `features/root_directory.py` | Populates tree nodes for ROOT `TDirectory` objects |
| `features/peak_search_feature.py` | Automatic and manual peak-finding helpers |
| `AGENT_CONTEXT.md` | Living architecture notes updated by agents after refactors |

---

## Session Persistence (Restart Flow)

1. Before restart → `BrowserTab.save_session_on_restart()` calls
   `SessionManager.save_last_files(open_files)` → writes `~/.pyhpge_gui/session.json`.
2. On next launch with `--last` → `main._resolve_initial_paths(use_last=True)`
   calls `_load_last_session_paths()` → returns only paths that still exist on disk.
3. `BrowserTab.apply_autosave()` (called 200 ms after startup) restores the
   expanded/selected tree state from the latest autosave JSON in
   `~/.pyhpge_gui/sessions/autosave/`.

---

## Error Handling

All exceptions must be reported via `ErrorDispatcher`, never silently swallowed
or printed to stdout.

```python
from modules.error_dispatcher import get_dispatcher, ErrorLevel

dispatcher = get_dispatcher()
try:
    ...
except Exception as e:
    dispatcher.emit(ErrorLevel.WARNING, "Short description",
                    context="ClassName.method_name", exception=e)
```

Use the appropriate level:
- **INFO** — expected/recoverable conditions (e.g. optional widget not found)
- **WARNING** — degraded functionality but app continues
- **ERROR** — operation failed; user should be notified (triggers messagebox)
- **CRITICAL** — app may be unstable

---

## Running Tests

```bash
# Install required system / Python dependencies
sudo apt-get install -y xvfb python3-tk   # headless display + Tk
pip3 install Pillow                        # PIL used by screenshot helpers

# Start a virtual framebuffer (required for headless tkinter)
Xvfb :99 -screen 0 1024x768x24 &
export DISPLAY=:99

# Run the full test suite (use python3 explicitly)
python3 -m pytest tests/ -v

# Run only the histogram workflow tests
python3 -m pytest tests/test_simple_test_1.py -v
```

Tests **must not** require ROOT to be installed — stub it via:

```python
import sys
from unittest.mock import MagicMock
sys.modules.setdefault("ROOT", MagicMock())
```

Session-related tests must use `tempfile.mkdtemp()` and patch
`os.path.expanduser` to avoid writing to the real home directory.

---

## Test Scenarios (Simple Test 1)

`tests/test_simple_test_1.py` covers the core histogram workflow that every
agent should keep passing:

1. **Open multiple histograms** — `HistogramTab.open_histogram()` for distinct
   `(root_path, path)` keys.
2. **Close histograms** — `remove_histogram()` / `close_current_histogram()`;
   verify `on_histogram_closed` callback receives the remaining count.
3. **Restart + session restore** — `save_last_files` → `_resolve_initial_paths`
   round-trip; missing files are filtered out.
4. **Open more histograms after restore** — tab accepts new opens after prior
   closes.
5. **Play with controls** — `HistogramPreviewRenderer` axis range vars
   (`_xmin_var`, `_xmax_var`, `_ymin_var`, `_ymax_var`) and log-scale toggles
   (`_logx_var`, `_logy_var`).
6. **Switch between histograms** — `show_histogram(key)` updates
   `_current_histogram_key`.

---

## Coding Conventions

- **Imports**: stdlib → third-party → project-local; alphabetical within groups.
- **Type hints**: use `from __future__ import annotations`; annotate all public
  method signatures.
- **Docstrings**: one-line summary for simple methods; full Args/Returns for
  public API.
- **No bare `except`**: always catch a specific exception type or `Exception`
  and emit via `ErrorDispatcher`.
- **No UI in modules/features**: only `tab_managers/` and `gui_base/` may
  import `tkinter`.
- **Minimal changes**: prefer surgical edits over large rewrites; keep diffs
  small and reviewable.

---

## Agent Workflow Checklist

Before opening a PR, an agent should verify:

- [ ] All tests in `tests/test_simple_test_1.py` pass.
- [ ] No new bare `except` blocks introduced.
- [ ] `AGENT_CONTEXT.md` updated if the architecture changed.
- [ ] No new direct imports of `ROOT` outside `gui_base/` or `tab_managers/`
      (modules receive the ROOT reference via constructor injection).
- [ ] CodeQL security scan returns 0 alerts.

## User Guide (2026)

### Opening ROOT Files
Use the browser tab's open file button to select ROOT files. The tab delegates file operations to the `RootFileManager` module. Double-click a histogram object in the tree to open it in the histogram tab.

### Browsing and Navigation
The tree view displays ROOT file contents. Double-click histograms to open them in the histogram manager.

### Session Persistence
The browser tab automatically saves the last opened files. Use `--last` at startup to restore the previous session.

### Histogram Tab
Each opened histogram gets its own preview with a full control panel:

| Control | Behaviour |
|---------|-----------|
| **Title** | Edits the plot title (top row; pre-filled from histogram) |
| **X / Y range** | Sets the visible axis range (`SetRangeUser`); does not alter binning |
| **X / Y label** | Edits the axis title on the rendered plot |
| **Log X / Log Y** | Toggles logarithmic scale |
| **Show Markers** | Shows/hides peak marker lines without clearing the peak list |
| **Reset** | Restores all controls to the histogram's original defaults |
| **Peaks treeview** | Lists found/manual peaks; double-click to edit, Delete to remove |
| **Manual (keV)** | Type an energy and press Enter or Add to add a manual peak |
| **Find Peaks** | Runs automatic peak detection on the current histogram |
| **Clear** | Removes all peaks from the list |

**Scroll on any range entry** to adjust the value quickly:
- *Linear mode*: step = 1% of axis max per scroll tick
- *Log mode* (Log X/Y active): multiplicative step ≈ 1.12× per tick

Entry values are clamped to the histogram's original axis max — no value can exceed the original data range.

All entry changes (typing, paste, scroll) trigger an auto-render after a 150 ms debounce.

### Modular Architecture
- Tabs are UI managers.
- Modules handle domain logic and file operations (no tkinter).
- Features are pure computation helpers invoked by modules.

See `AGENT_CONTEXT.md` for full architecture details and `CHANGELOG.md` for history.

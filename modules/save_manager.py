"""Save manager module — thin coordinator.

All serialisation logic lives in the feature layer:
  - ``features.peak_export_feature.PeakExportFeature``  (peaks → CSV / JSON)
  - ``features.fit_export_feature.FitExportFeature``    (fits  → CSV / JSON / PDF report)
  - ``features.renderer_feature.RendererFeature``       (histogram → PNG / PDF preview)

``SaveManager`` owns only coordination: it instantiates the features, exposes
a stable public API for tab-manager callers, and delegates every substantive
operation to the appropriate feature.
"""

from __future__ import annotations

import os
import shutil
import warnings
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from features.renderer_feature import RendererFeature
from features.peak_export_feature import PeakExportFeature, _fit_state_val
from features.fit_export_feature import FitExportFeature


# ---------------------------------------------------------------------------
# Module-level UI helpers (thin wrappers around tkinter dialogs)
# ---------------------------------------------------------------------------

def ask_saveas(*, title: str, initialdir: str, initialfile: str,
               defaultextension: str,
               filetypes: list[tuple[str, str]]) -> str | None:
    return filedialog.asksaveasfilename(
        title=title, initialdir=initialdir, initialfile=initialfile,
        defaultextension=defaultextension, filetypes=filetypes,
    )


def ask_directory(*, title: str) -> str | None:
    return filedialog.askdirectory(title=title)


def info(title: str, message: str) -> None:
    messagebox.showinfo(title, message)


def warning(title: str, message: str) -> None:
    messagebox.showwarning(title, message)


def error(title: str, message: str) -> None:
    messagebox.showerror(title, message)


# ---------------------------------------------------------------------------
# SaveManager
# ---------------------------------------------------------------------------

class SaveManager:
    """Thin coordinator that delegates all I/O work to feature instances."""

    def __init__(self) -> None:
        self.renderer_feature = RendererFeature()
        self._peak_export    = PeakExportFeature()
        self._fit_export     = FitExportFeature()
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")

    # ------------------------------------------------------------------
    # Rendering (delegated to RendererFeature)
    # ------------------------------------------------------------------

    def default_save(
        self,
        root,
        obj,
        default_name: str = "object",
        output_dir: str | None = None,
        width: int = 1920,
        height: int | None = None,
    ) -> list[str]:
        """Quick default save to PNG and PDF."""
        if height is None:
            height = int(width * 9 / 16)
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "outputs", "screenshots")
        os.makedirs(output_dir, exist_ok=True)
        png_path = os.path.join(output_dir, f"{default_name}.png")
        pdf_path = os.path.join(output_dir, f"{default_name}.pdf")
        self.renderer_feature.render_to_file(root, obj, png_path, width, height)
        self.renderer_feature.render_to_file(root, obj, pdf_path, width, height)
        return [png_path, pdf_path]

    def save_render_files(
        self,
        root,
        obj,
        directory: str,
        filename: str,
        width: int,
        height: int,
        render_options: dict | None = None,
        save_png: bool = True,
        save_pdf: bool = True,
        rendered_paths: dict | None = None,
    ) -> list[str]:
        """Copy or render PNG / PDF files into *directory*."""
        if render_options is None:
            render_options = {}
        os.makedirs(directory, exist_ok=True)
        saved: list[str] = []
        temp_paths: dict = rendered_paths or {}

        if not temp_paths and self.renderer_feature is not None:
            if save_png:
                try:
                    temp_paths["png"] = self.renderer_feature.render_to_temp_image(
                        root, obj, int(width), int(height), render_options
                    )
                except Exception:
                    pass
            if save_pdf:
                try:
                    temp_paths["pdf"] = self.renderer_feature.render_to_temp_pdf(
                        root, obj, int(width), int(height), render_options
                    )
                except Exception:
                    pass

        for fmt, flag in (("png", save_png), ("pdf", save_pdf)):
            if flag and temp_paths.get(fmt):
                dst = os.path.join(directory, f"{filename}.{fmt}")
                shutil.copy(temp_paths[fmt], dst)
                saved.append(dst)

        for fmt in ("png", "pdf"):
            if temp_paths.get(fmt):
                try:
                    self.renderer_feature.release_temp_image(temp_paths[fmt])
                except Exception:
                    pass

        return saved

    def save_screenshot(
        self,
        root,
        obj,
        directory: str,
        filename: str,
        width: int = 1920,
        height: int | None = None,
        render_options: dict | None = None,
        save_png: bool = True,
        save_pdf: bool = True,
        rendered_paths: dict | None = None,
    ) -> list[str]:
        """Convenience wrapper around ``save_render_files``."""
        return self.save_render_files(
            root, obj, directory, filename,
            width, height if height is not None else int(width * 9 / 16),
            render_options=render_options,
            save_png=save_png, save_pdf=save_pdf,
            rendered_paths=rendered_paths,
        )

    # ------------------------------------------------------------------
    # Peak export (delegated to PeakExportFeature)
    # ------------------------------------------------------------------

    def export_peaks(self, peak_finder, directory: str, name: str) -> str:
        """Export peaks to CSV; accepts a list, tuple, or feature object."""
        csv_path = os.path.join(directory, f"{name}_peaks.csv")
        try:
            if isinstance(peak_finder, (list, tuple)):
                self._peak_export.export_csv(list(peak_finder), name, csv_path)
                return csv_path
            if hasattr(peak_finder, "peaks") and isinstance(
                getattr(peak_finder, "peaks"), (list, tuple)
            ):
                self._peak_export.export_csv(
                    list(getattr(peak_finder, "peaks")), name, csv_path
                )
                return csv_path
            for method in ("export_peaks", "export_peaks_to_file",
                           "_export_peaks_to_file"):
                if hasattr(peak_finder, method):
                    getattr(peak_finder, method)(csv_path)
                    return csv_path
            if hasattr(peak_finder, "get_peaks") and callable(peak_finder.get_peaks):
                peaks = peak_finder.get_peaks()
                if isinstance(peaks, (list, tuple)):
                    self._peak_export.export_csv(list(peaks), name, csv_path)
                    return csv_path
        except Exception:
            raise
        raise AttributeError(
            "Provided peak_finder has no known export method or peaks list"
        )

    def export_peaks_csv(
        self,
        peaks: list[dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
        fit_states: dict | None = None,
    ) -> str | None:
        return self._peak_export.export_csv(
            peaks, histogram_name, filepath, fit_states=fit_states
        )

    def export_peaks_json(
        self,
        peaks: list[dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
        fit_states: dict | None = None,
    ) -> str | None:
        return self._peak_export.export_json(
            peaks, histogram_name, filepath, fit_states=fit_states
        )

    # ------------------------------------------------------------------
    # Fit export (delegated to FitExportFeature)
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_state_val(fit_state: dict, key: str, default=""):
        """Compat shim — delegates to the module-level helper in peak_export_feature."""
        return _fit_state_val(fit_state, key, default)

    def export_fit_results_csv(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        return self._fit_export.export_csv(fit_states, histogram_name, filepath)

    def export_fit_results_json(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        return self._fit_export.export_json(fit_states, histogram_name, filepath)

    def export_single_fit(
        self,
        fit_state: dict,
        histogram_name: str = "histogram",
        export_format: str = "csv",
        filepath: str | None = None,
    ) -> str | None:
        fit_id = fit_state.get("tab_id", 1)
        fit_states_dict = {fit_id: fit_state}
        if export_format == "json":
            return self._fit_export.export_json(fit_states_dict, histogram_name, filepath)
        return self._fit_export.export_csv(fit_states_dict, histogram_name, filepath)

    def export_fit_results(
        self,
        fit_states: dict,
        directory: str,
        name: str,
        csv: bool = True,
        json: bool = True,
    ) -> list[str]:
        saved: list[str] = []
        if csv:
            path = os.path.join(directory, f"{name}_fit_results.csv")
            try:
                self._fit_export.export_csv(fit_states, name, path)
                saved.append(path)
            except Exception:
                pass
        if json:
            path = os.path.join(directory, f"{name}_fit_results.json")
            try:
                self._fit_export.export_json(fit_states, name, path)
                saved.append(path)
            except Exception:
                pass
        return saved

    def export_fit_report_pdf(
        self,
        root,
        hist,
        fit_states: dict[int, dict],
        directory: str,
        name: str,
    ) -> str | None:
        return self._fit_export.export_report_pdf(
            root, hist, fit_states, directory, name
        )

    # ------------------------------------------------------------------
    # Batch report (coordinates both feature exports)
    # ------------------------------------------------------------------

    def create_batch_report(
        self,
        batch_results: list[dict],
        output_dir: str | None = None,
    ) -> str | None:
        if not batch_results:
            return None
        import csv as _csv
        import datetime
        if output_dir is None:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(
                self.default_output_dir, "batch_reports", f"batch_{ts}"
            )
        os.makedirs(output_dir, exist_ok=True)

        summary_path = os.path.join(output_dir, "batch_summary.csv")
        with open(summary_path, "w", newline="", encoding="utf-8") as fh:
            writer = _csv.writer(fh)
            writer.writerow([
                "Histogram", "Peaks_Found", "Fits_Completed",
                "Fits_Failed", "Processing_Status",
            ])
            for result in batch_results:
                writer.writerow([
                    result.get("histogram_name", "unknown"),
                    result.get("peaks_found", 0),
                    result.get("fits_completed", 0),
                    result.get("fits_failed", 0),
                    result.get("status", "unknown"),
                ])

        for result in batch_results:
            hist_name  = result.get("histogram_name", "unknown")
            fit_states = result.get("fit_states", {})
            if fit_states:
                self._fit_export.export_csv(
                    fit_states, hist_name,
                    os.path.join(output_dir, f"{hist_name}_fits.csv"),
                )
                self._fit_export.export_json(
                    fit_states, hist_name,
                    os.path.join(output_dir, f"{hist_name}_fits.json"),
                )
            peaks = result.get("peaks", [])
            if peaks:
                self._peak_export.export_csv(
                    peaks, hist_name,
                    os.path.join(output_dir, f"{hist_name}_peaks.csv"),
                )

        return output_dir

    def ask_saveas_default(self, default_name: str) -> str | None:
        try:
            return ask_saveas(
                title="Save As",
                initialdir=self.default_output_dir,
                initialfile=default_name,
                defaultextension="",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            )
        except Exception:
            return None

    # ------------------------------------------------------------------
    # High-level entry point
    # ------------------------------------------------------------------

    def delegate_save(
        self,
        *,
        root=None,
        obj=None,
        directory: str,
        name: str,
        width: int = 1920,
        height: int | None = None,
        render_options: dict | None = None,
        png: bool = True,
        pdf: bool = True,
        rendered_paths: dict | None = None,
        fit_states: dict | None = None,
    ) -> list[str]:
        """Coordinate a full save: image renders + optional fit exports."""
        if height is None:
            height = int(width * 9 / 16)
        os.makedirs(directory, exist_ok=True)
        saved: list[str] = []

        if png or pdf:
            try:
                saved.extend(
                    self.save_screenshot(
                        root, obj, directory, name, width, height,
                        render_options=render_options,
                        save_png=png, save_pdf=pdf,
                        rendered_paths=rendered_paths,
                    )
                )
            except RuntimeError:
                pass

        if fit_states:
            saved.extend(
                self.export_fit_results(
                    fit_states, directory, name, csv=True, json=True
                )
            )

        return saved


# ---------------------------------------------------------------------------
# AdvancedSaveDialog — deprecated; kept for backward compatibility
# ---------------------------------------------------------------------------

class AdvancedSaveDialog(tk.Toplevel):
    """Deprecated dialog.  Use ``SaveManager.delegate_save()`` instead."""

    def __init__(
        self,
        parent: tk.Widget,
        root,
        hist,
        default_name: str = "histogram",
        peak_finder=None,
        subdirectory: str | None = None,
        render_options: dict | None = None,
        fit_states: dict | None = None,
    ) -> None:
        warnings.warn(
            "AdvancedSaveDialog is deprecated; use SaveManager.delegate_save().",
            DeprecationWarning,
        )
        super().__init__(parent)
        self.title("Advanced Save Options")
        self.geometry("800x600")
        self.resizable(True, False)
        self.root = root
        self.hist = hist
        self.peak_finder   = peak_finder
        self.fit_states    = fit_states or {}
        self.save_manager  = SaveManager()
        self.result        = None
        self.subdirectory  = subdirectory or default_name
        self.render_options = render_options or {}
        self.transient(parent)
        self.grab_set()
        self._build_ui(default_name)

    def _build_ui(self, default_name: str) -> None:
        main_frame = ttk.Frame(self, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame, text="File Path & Name",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))
        ttk.Label(path_frame, text="Directory:").pack(anchor="w")
        self.dir_var = tk.StringVar(
            value=os.path.join("outputs", self.subdirectory)
        )
        ttk.Entry(path_frame, textvariable=self.dir_var).pack(fill=tk.X, pady=(4, 0))
        ttk.Button(path_frame, text="Browse",
                   command=self._browse_dir).pack(anchor="w", pady=(4, 0))
        ttk.Label(path_frame, text="Filename (no extension):").pack(
            anchor="w", pady=(12, 0)
        )
        self.name_var = tk.StringVar(value=default_name)
        ttk.Entry(path_frame, textvariable=self.name_var).pack(fill=tk.X, pady=(4, 0))

        ttk.Label(
            main_frame, text="Resolution",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(12, 8))
        res_frame = ttk.Frame(main_frame)
        res_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))
        ttk.Label(res_frame, text="Width (px):").grid(row=0, column=0, sticky="e", padx=(0, 6))
        self.width_var = tk.StringVar(value="1920")
        ttk.Entry(res_frame, textvariable=self.width_var, width=10).grid(row=0, column=1, sticky="w")
        ttk.Label(res_frame, text="Height (px):").grid(row=0, column=2, sticky="e", padx=(12, 6))
        self.height_var = tk.StringVar(value="1080")
        ttk.Entry(res_frame, textvariable=self.height_var, width=10).grid(row=0, column=3, sticky="w")
        for col, label, cmd in (
            (4, "16:9", self._set_169),
            (5, "4:3",  self._set_43),
            (6, "1:1",  self._set_11),
        ):
            ttk.Button(res_frame, text=label, command=cmd).grid(
                row=0, column=col, padx=(4 if col > 4 else 12, 0)
            )

        ttk.Label(
            main_frame, text="Export Formats",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w", pady=(12, 8))
        fmt_frame = ttk.Frame(main_frame)
        fmt_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))
        self.png_var = tk.BooleanVar(value=True)
        self.pdf_var = tk.BooleanVar(value=True)
        self.csv_var = tk.BooleanVar(value=False)
        self.fit_csv_var  = tk.BooleanVar(value=False)
        self.fit_json_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fmt_frame, text="PNG", variable=self.png_var).pack(anchor="w")
        ttk.Checkbutton(fmt_frame, text="PDF", variable=self.pdf_var).pack(anchor="w", pady=(4, 0))
        if self.peak_finder is not None:
            ttk.Checkbutton(fmt_frame, text="CSV (Peaks)",
                            variable=self.csv_var).pack(anchor="w", pady=(4, 0))
        if self.fit_states:
            ttk.Checkbutton(fmt_frame, text="CSV (Fit Results)",
                            variable=self.fit_csv_var).pack(anchor="w", pady=(4, 0))
            ttk.Checkbutton(fmt_frame, text="JSON (Fit Results)",
                            variable=self.fit_json_var).pack(anchor="w", pady=(4, 0))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.dir_var.get(),
                                    title="Select Save Directory")
        if d:
            self.dir_var.set(d)

    def _set_169(self) -> None:
        self.height_var.set(str(int(int(self.width_var.get()) * 9 / 16)))

    def _set_43(self) -> None:
        self.height_var.set(str(int(int(self.width_var.get()) * 3 / 4)))

    def _set_11(self) -> None:
        self.height_var.set(self.width_var.get())

    def _save(self) -> None:
        try:
            directory = self.dir_var.get().strip()
            name      = self.name_var.get().strip()
            width     = int(self.width_var.get())
            height    = int(self.height_var.get())
            if not directory or not name:
                messagebox.showerror("Invalid input", "Directory and filename required")
                return
            if width < 100 or height < 100:
                messagebox.showerror("Invalid resolution",
                                     "Width and height must be >= 100 px")
                return
            os.makedirs(directory, exist_ok=True)
            saved = self.save_manager.delegate_save(
                root=self.root, obj=self.hist,
                directory=directory, name=name,
                width=width, height=height,
                render_options=self.render_options,
                png=self.png_var.get(), pdf=self.pdf_var.get(),
                fit_states=(
                    self.fit_states
                    if (self.fit_csv_var.get() or self.fit_json_var.get())
                    else None
                ),
            )
            if self.csv_var.get() and self.peak_finder:
                try:
                    peaks = None
                    if isinstance(self.peak_finder, (list, tuple)):
                        peaks = list(self.peak_finder)
                    elif hasattr(self.peak_finder, "peaks"):
                        peaks = list(getattr(self.peak_finder, "peaks"))
                    if peaks:
                        p = os.path.join(directory, f"{name}_peaks.csv")
                        self.save_manager.export_peaks_csv(peaks, name, p)
                        saved.append(p)
                except Exception as exc:
                    messagebox.showerror("Peaks export failed", f"Error: {exc}")
            if saved:
                messagebox.showinfo(
                    "Success",
                    "Saved to:\n" + "\n".join(os.path.basename(f) for f in saved),
                )
            else:
                messagebox.showinfo("Done", "No files were created")
            self.destroy()
        except ValueError:
            messagebox.showerror("Invalid input", "Width and height must be numbers")
        except Exception as exc:
            messagebox.showerror("Save failed", f"Error: {exc}")


# Note: callers should import ``AdvancedSaveDialog`` from this module.

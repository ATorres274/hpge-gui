"""Centralized save functionality for all features."""

from __future__ import annotations

import os
import warnings
import tkinter as tk
from tkinter import ttk, filedialog, messagebox



# Export UI helpers (moved from features/export_ui.py)
def ask_saveas(*, title: str, initialdir: str, initialfile: str, defaultextension: str, filetypes: list[tuple[str, str]]) -> str | None:
    return filedialog.asksaveasfilename(
        title=title,
        initialdir=initialdir,
        initialfile=initialfile,
        defaultextension=defaultextension,
        filetypes=filetypes,
    )


def ask_directory(*, title: str) -> str | None:
    return filedialog.askdirectory(title=title)


def info(title: str, message: str) -> None:
    messagebox.showinfo(title, message)


def warning(title: str, message: str) -> None:
    messagebox.showwarning(title, message)


def error(title: str, message: str) -> None:
    messagebox.showerror(title, message)

import shutil
from features.renderer_feature import RendererFeature


class SaveManager:
    """Manages save operations for ROOT objects with default and advanced options."""

    def __init__(self) -> None:
        # Default output directory for exports
        # Renderer feature used to perform rendering when callers prefer SaveManager
        # to render on their behalf. Tabs may instead render themselves and pass
        # `rendered_paths` into the save methods.
        self.renderer_feature: RendererFeature | None = RendererFeature()
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")

    def default_save(
        self,
        root,
        obj,
        default_name: str = "object",
        output_dir: str | None = None,
        width: int = 1920,
        height: int | None = None,
    ) -> list[str]:
        """
        Perform a quick default save to PNG and PDF.

        Args:
            root: ROOT module
            obj: ROOT object to save (TH1, TH2, etc.)
            default_name: Base filename without extension
            output_dir: Output directory (defaults to outputs/screenshots)
            width: Canvas width in pixels
            height: Canvas height in pixels (defaults to 16:9 aspect ratio)

        Returns:
            True if save successful, False otherwise
        """
        if height is None:
            height = int(width * 9 / 16)

        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "outputs", "screenshots")

        os.makedirs(output_dir, exist_ok=True)

        png_path = os.path.join(output_dir, f"{default_name}.png")
        pdf_path = os.path.join(output_dir, f"{default_name}.pdf")

        self.renderer.render_to_file(root, obj, png_path, width, height)
        self.renderer.render_to_file(root, obj, pdf_path, width, height)

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
        """
        Save PNG and/or PDF renders of a ROOT object.

        Args:
            root: ROOT module
            obj: ROOT object to render
            directory: Output directory
            filename: Base filename without extension
            width: Canvas width in pixels
            height: Canvas height in pixels
            render_options: Dictionary with rendering options
            save_png: Whether to save PNG
            save_pdf: Whether to save PDF

        Returns:
            List of saved file paths
        """
        # This method no longer performs rendering. Callers must provide
        # paths to already-rendered files via `rendered_paths` mapping:
        # {'png': '/tmp/foo.png', 'pdf': '/tmp/foo.pdf'}.
        if render_options is None:
            render_options = {}

        os.makedirs(directory, exist_ok=True)
        saved_files = []

        # If the caller provided rendered file paths, use them. Otherwise,
        # fall back to the renderer feature (if available) to produce temporary
        # render outputs which we then copy into the destination directory.
        temp_paths: dict = rendered_paths or {}

        # If no pre-rendered files and we have a renderer feature, produce them
        if not temp_paths and self.renderer_feature is not None:
            # Create temporary renders as needed
            if save_png:
                try:
                    temp_paths["png"] = self.renderer_feature.render_to_temp_image(root, obj, int(width), int(height), render_options)
                except Exception:
                    pass
            if save_pdf:
                try:
                    temp_paths["pdf"] = self.renderer_feature.render_to_temp_pdf(root, obj, int(width), int(height), render_options)
                except Exception:
                    pass

        if save_png and temp_paths.get("png"):
            dst = os.path.join(directory, f"{filename}.png")
            shutil.copy(temp_paths.get("png"), dst)
            saved_files.append(dst)

        if save_pdf and temp_paths.get("pdf"):
            dst = os.path.join(directory, f"{filename}.pdf")
            shutil.copy(temp_paths.get("pdf"), dst)
            saved_files.append(dst)

        # Release any temporary images created by the renderer feature
        for key in ("png", "pdf"):
            if temp_paths.get(key):
                try:
                    if self.renderer_feature is not None:
                        self.renderer_feature.release_temp_image(temp_paths.get(key))
                except Exception:
                    pass

        return saved_files

    # New convenience methods to delegate feature-specific exports
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
        """Convenience wrapper around `save_render_files`.

            This method is intended to be called by feature modules when they
            want to request screenshots (histogram, fit plots, etc.).
            """
        return self.save_render_files(
            root,
            obj,
            directory,
            filename,
            width,
            height if height is not None else int(width * 9 / 16),
            render_options=render_options,
            save_png=save_png,
            save_pdf=save_pdf,
            rendered_paths=rendered_paths,
        )

    def export_peaks(self, peak_finder, directory: str, name: str) -> str:
        """Export peaks using the provided peak finder feature.

        This method will try a few well-known export method names on the
        `peak_finder` object, allowing different feature implementations to
        provide their own export function.
        Returns the path to the created CSV file.
        """
        csv_path = os.path.join(directory, f"{name}_peaks.csv")
        # If a simple list of peaks is provided, use the CSV exporter
        try:
            if isinstance(peak_finder, (list, tuple)):
                self.export_peaks_csv(list(peak_finder), name, csv_path)
                return csv_path

            # If object exposes `peaks` attribute, use it
            if hasattr(peak_finder, "peaks") and isinstance(getattr(peak_finder, "peaks"), (list, tuple)):
                self.export_peaks_csv(list(getattr(peak_finder, "peaks")), name, csv_path)
                return csv_path

            # Prefer a public method if present
            if hasattr(peak_finder, "export_peaks"):
                peak_finder.export_peaks(csv_path)
                return csv_path
            if hasattr(peak_finder, "export_peaks_to_file"):
                peak_finder.export_peaks_to_file(csv_path)
                return csv_path
            if hasattr(peak_finder, "_export_peaks_to_file"):
                peak_finder._export_peaks_to_file(csv_path)
                return csv_path

            # Fallback: try to access `get_peaks()` method
            if hasattr(peak_finder, "get_peaks") and callable(peak_finder.get_peaks):
                peaks = peak_finder.get_peaks()
                if isinstance(peaks, (list, tuple)):
                    self.export_peaks_csv(list(peaks), name, csv_path)
                    return csv_path

        except Exception:
            # Let caller handle exceptions
            raise

        raise AttributeError("Provided peak_finder has no known export method or peaks list")


    # --- Inlined export_manager functionality ---
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

    @staticmethod
    def _fit_state_val(fit_state: dict, key: str, default=""):
        """Extract a plain value from a fit state that may use tkinter StringVar.

        Supports both the new ``FitModule`` plain-dict states (``"fit_func"``,
        ``"energy"``, ``"width"`` as native Python values) and the legacy
        tkinter-Var based states (``"fit_func_var"``, ``"energy_var"``,
        ``"width_var"``).
        """
        # New FitModule plain-Python key
        val = fit_state.get(key)
        if val is not None:
            return val
        # Legacy tkinter-Var key (e.g. "fit_func_var" → .get())
        var = fit_state.get(f"{key}_var")
        if var is not None and hasattr(var, "get") and callable(var.get):
            try:
                return var.get()
            except Exception:
                pass
        return default

    def export_fit_results_csv(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        if not fit_states:
            return None
        if not filepath:
            raise ValueError("filepath is required")
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            import csv

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Fit_ID",
                    "Fit_Function",
                    "Energy_keV",
                    "Width_keV",
                    "Chi2",
                    "NDF",
                    "Reduced_Chi2",
                    "Status",
                    "Parameters",
                    "Errors",
                    "FWHM_keV",
                    "Centroid_keV",
                    "Area",
                ])
                _FWHM = 2.355
                _SQRT2PI = 2.506628
                for tab_id, fit_state in sorted(fit_states.items()):
                    cached = fit_state.get("cached_results")
                    if cached is None or "error" in cached:
                        continue

                    fit_func = self._fit_state_val(fit_state, "fit_func", "unknown")
                    energy   = self._fit_state_val(fit_state, "energy", "")
                    width    = self._fit_state_val(fit_state, "width", "")

                    chi2 = cached.get("chi2", "")
                    ndf = cached.get("ndf", "")
                    reduced_chi2 = chi2 / ndf if ndf and ndf > 0 else ""
                    status = cached.get("status", "")
                    parameters = cached.get("parameters", [])
                    errors = cached.get("errors", [])

                    fwhm = centroid = area = ""
                    # Gaussian peak annotations for gaus and compound gaus models
                    if (fit_func == "gaus" or (isinstance(fit_func, str) and fit_func.startswith("gaus+"))) and len(parameters) >= 3:
                        constant, mean, sigma = parameters[0], parameters[1], parameters[2]
                        fwhm = _FWHM * sigma
                        centroid = mean
                        area = constant * sigma * _SQRT2PI

                    writer.writerow([
                        tab_id,
                        fit_func,
                        energy,
                        width,
                        f"{chi2:.6f}" if chi2 else "",
                        ndf,
                        f"{reduced_chi2:.6f}" if reduced_chi2 else "",
                        status,
                        "; ".join(f"{p:.6f}" for p in parameters),
                        "; ".join(f"{e:.6f}" for e in errors),
                        f"{fwhm:.3f}" if fwhm else "",
                        f"{centroid:.3f}" if centroid else "",
                        f"{area:.1f}" if area else "",
                    ])
            return filepath
        except Exception:
            raise

    def export_fit_results_json(
        self,
        fit_states: dict[int, dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
    ) -> str | None:
        if not fit_states:
            return None
        if not filepath:
            raise ValueError("filepath is required")
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            export_data = {
                "histogram": histogram_name,
                "export_timestamp": datetime.now().isoformat(),
                "fits": [],
            }
            _FWHM = 2.355
            _SQRT2PI = 2.506628
            for tab_id, fit_state in sorted(fit_states.items()):
                cached = fit_state.get("cached_results")
                if cached is None:
                    continue

                fit_func = self._fit_state_val(fit_state, "fit_func", "unknown")
                energy   = self._fit_state_val(fit_state, "energy", "")
                width    = self._fit_state_val(fit_state, "width", "")

                fit_data: dict = {
                    "fit_id": tab_id,
                    "fit_function": fit_func,
                    "energy_keV": float(energy) if energy else None,
                    "width_keV": float(width) if width else None,
                }

                if "error" in cached:
                    fit_data["error"] = cached["error"]
                else:
                    chi2 = cached.get("chi2", 0)
                    ndf = cached.get("ndf", 0)
                    parameters = cached.get("parameters", [])
                    errors = cached.get("errors", [])

                    fit_data.update({
                        "chi2": chi2,
                        "ndf": ndf,
                        "reduced_chi2": chi2 / ndf if ndf > 0 else None,
                        "status": cached.get("status", 0),
                        "parameters": [
                            {"index": i, "value": p, "error": errors[i] if i < len(errors) else 0}
                            for i, p in enumerate(parameters)
                        ],
                    })

                    is_gaus = fit_func == "gaus" or (isinstance(fit_func, str) and fit_func.startswith("gaus+"))
                    if is_gaus and len(parameters) >= 3:
                        constant, mean, sigma = parameters[0], parameters[1], parameters[2]
                        fit_data["annotations"] = {
                            "fwhm_keV": _FWHM * sigma,
                            "centroid_keV": mean,
                            "area": constant * sigma * _SQRT2PI,
                        }
                    elif fit_func == "landau" and len(parameters) >= 3:
                        fit_data["annotations"] = {
                            "most_probable_value_keV": parameters[1],
                            "width_keV": parameters[2],
                        }

                export_data["fits"].append(fit_data)

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)

            return filepath
        except Exception:
            raise

    def export_single_fit(self, fit_state: dict, histogram_name: str = "histogram", format: str = "csv", filepath: str | None = None) -> str | None:
        tab_id = fit_state.get("tab_id", 1)
        fit_states_dict = {tab_id: fit_state}
        if format == "json":
            return self.export_fit_results_json(fit_states_dict, histogram_name, filepath)
        return self.export_fit_results_csv(fit_states_dict, histogram_name, filepath)

    def export_peaks_csv(
        self,
        peaks: list[dict],
        histogram_name: str = "histogram",
        filepath: str | None = None,
        fit_states: dict | None = None,
    ) -> str | None:
        """Export peaks (and optionally fit results) to a single CSV file.

        When *fit_states* is supplied the fit results are appended as a
        second section after the peak rows, so callers get one file with
        all analysis results.
        """
        if not peaks:
            return None
        if not filepath:
            raise ValueError("filepath is required")
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            import csv

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Peak_Number", "Energy_keV", "Counts"])
                for i, peak in enumerate(peaks, 1):
                    writer.writerow([
                        i,
                        f"{peak['energy']:.2f}",
                        f"{peak['counts']:.1f}",
                    ])

                if fit_states:
                    # Append fit results as a clearly-labelled second section.
                    writer.writerow([])
                    writer.writerow(["Fit Results"])
                    writer.writerow([
                        "Fit_ID", "Fit_Function", "Energy_keV", "Width_keV",
                        "Chi2", "NDF", "Reduced_Chi2", "Status",
                        "FWHM_keV", "Centroid_keV", "Area",
                    ])
                    _FWHM = 2.355
                    _SQRT2PI = 2.506628
                    for fit_id, fs in sorted(fit_states.items()):
                        cached = fs.get("cached_results")
                        if cached is None or "error" in cached:
                            continue
                        fit_func = self._fit_state_val(fs, "fit_func", "unknown")
                        energy   = self._fit_state_val(fs, "energy", "")
                        width    = self._fit_state_val(fs, "width", "")
                        chi2 = cached.get("chi2", "")
                        ndf  = cached.get("ndf", "")
                        reduced = chi2 / ndf if ndf and ndf > 0 else ""
                        params = cached.get("parameters", [])
                        fwhm = centroid = area = ""
                        if (fit_func == "gaus" or (isinstance(fit_func, str) and fit_func.startswith("gaus+"))) and len(params) >= 3:
                            fwhm = _FWHM * params[2]
                            centroid = params[1]
                            area = params[0] * params[2] * _SQRT2PI
                        writer.writerow([
                            fit_id, fit_func, energy, width,
                            f"{chi2:.6f}" if chi2 else "", ndf,
                            f"{reduced:.6f}" if reduced else "",
                            cached.get("status", ""),
                            f"{fwhm:.3f}" if fwhm else "",
                            f"{centroid:.3f}" if centroid else "",
                            f"{area:.1f}" if area else "",
                        ])
            return filepath
        except Exception:
            raise

    def export_peaks_json(self, peaks: list[dict], histogram_name: str = "histogram", filepath: str | None = None) -> str | None:
        """Export peak list to a JSON file.

        Args:
            peaks: List of peak dicts with ``energy``, ``counts``, ``source`` keys.
            histogram_name: Used as the top-level key in the output JSON.
            filepath: Destination file path (required).

        Returns:
            The filepath on success, ``None`` if peaks is empty.
        """
        if not peaks:
            return None
        if not filepath:
            raise ValueError("filepath is required")
        try:
            dir_path = os.path.dirname(filepath)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            import json

            export: dict = {
                "histogram": histogram_name,
                "peaks": [
                    {
                        "peak_number": i,
                        "energy_keV": round(float(p["energy"]), 4),
                        "counts": round(float(p["counts"]), 2) if p.get("counts") is not None else None,
                        "source": p.get("source", ""),
                    }
                    for i, p in enumerate(peaks, 1)
                ],
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2)
            return filepath
        except Exception:
            raise

    def create_batch_report(self, batch_results: list[dict[str, Any]], output_dir: str | None = None) -> str | None:
        if not batch_results:
            return None
        if output_dir is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = os.path.join(self.default_output_dir, "batch_reports", f"batch_{timestamp}")
        try:
            os.makedirs(output_dir, exist_ok=True)
            import csv
            for_export = batch_results

            summary_path = os.path.join(output_dir, "batch_summary.csv")
            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Histogram",
                    "Peaks_Found",
                    "Fits_Completed",
                    "Fits_Failed",
                    "Processing_Status",
                ])
                for result in for_export:
                    writer.writerow([
                        result.get("histogram_name", "unknown"),
                        result.get("peaks_found", 0),
                        result.get("fits_completed", 0),
                        result.get("fits_failed", 0),
                        result.get("status", "unknown"),
                    ])

            for result in for_export:
                hist_name = result.get("histogram_name", "unknown")
                fit_states = result.get("fit_states", {})
                if fit_states:
                    fit_csv_path = os.path.join(output_dir, f"{hist_name}_fits.csv")
                    self.export_fit_results_csv(fit_states, hist_name, fit_csv_path)
                    fit_json_path = os.path.join(output_dir, f"{hist_name}_fits.json")
                    self.export_fit_results_json(fit_states, hist_name, fit_json_path)
                peaks = result.get("peaks", [])
                if peaks:
                    peaks_path = os.path.join(output_dir, f"{hist_name}_peaks.csv")
                    self.export_peaks_csv(peaks, hist_name, peaks_path)

            return output_dir
        except Exception:
            raise

    # Ensure existing wrapper uses inlined methods
    def export_fit_results(self, fit_states: dict, directory: str, name: str, csv: bool = True, json: bool = True) -> list[str]:
        saved = []
        if csv:
            csv_path = os.path.join(directory, f"{name}_fit_results.csv")
            try:
                self.export_fit_results_csv(fit_states, name, csv_path)
                saved.append(csv_path)
            except Exception:
                pass
        if json:
            json_path = os.path.join(directory, f"{name}_fit_results.json")
            try:
                self.export_fit_results_json(fit_states, name, json_path)
                saved.append(json_path)
            except Exception:
                pass
        return saved

    def delegate_save(self,
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
                      fit_states: dict | None = None) -> list[str]:
        """High-level save entry point used by tabs/features.

        The feature code should call this method with the relevant pieces
        (root/object for screenshots, `peak_finder` for peak CSV export,
        and `fit_states` for fit exports). This centralizes where files are
        written while leaving UI and feature-specific behavior to the
        respective feature modules.
        """
        if height is None:
            height = int(width * 9 / 16)

        os.makedirs(directory, exist_ok=True)
        saved = []

        # Screenshots (PNG/PDF) — expect pre-rendered files from the caller
        if png or pdf:
            try:
                saved.extend(self.save_screenshot(root, obj, directory, name, width, height, render_options=render_options, save_png=png, save_pdf=pdf, rendered_paths=rendered_paths))
            except RuntimeError:
                # If no rendered files were provided, do not attempt to render here.
                pass

        # Note: peak-finder objects are not handled here. Pushing responsibility
        # to the UI/feature layer ensures SaveManager only writes files when
        # given plain data structures (lists/dicts) and does not introspect
        # feature objects.

        # Fit results
        if fit_states:
            saved.extend(self.export_fit_results(fit_states, directory, name, csv=True, json=True))

        return saved


class AdvancedSaveDialog(tk.Toplevel):
    """Dialog for advanced histogram save options.

    UI dialogs should be implemented by feature modules; `SaveManager`
    provides delegate methods to perform exports and screenshots.
    """

    def __init__(self, parent: tk.Widget, root, hist, default_name: str = "histogram", peak_finder=None, subdirectory: str = None, render_options: dict = None, fit_states: dict = None) -> None:
        warnings.warn(
            "AdvancedSaveDialog is deprecated; move UI to feature modules and call SaveManager.delegate_save().",
            DeprecationWarning,
        )

        super().__init__(parent)
        self.title("Advanced Save Options")
        self.geometry("800x600")
        self.resizable(True, False)

        self.root = root
        self.hist = hist
        self.peak_finder = peak_finder
        self.fit_states = fit_states if fit_states else {}
        self.save_manager = SaveManager()
        self.result = None
        self.subdirectory = subdirectory if subdirectory else default_name
        self.render_options = render_options if render_options else {}

        # Make dialog modal
        self.transient(parent)
        self.grab_set()

        self._build_ui(default_name)

    def _build_ui(self, default_name: str) -> None:
        """Build the dialog UI."""
        main_frame = ttk.Frame(self, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # File path section
        ttk.Label(main_frame, text="File Path & Name", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))

        ttk.Label(path_frame, text="Directory:").pack(anchor="w")
        self.dir_var = tk.StringVar(value=os.path.join("outputs", self.subdirectory))
        dir_entry = ttk.Entry(path_frame, textvariable=self.dir_var)
        dir_entry.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(path_frame, text="Browse", command=self._browse_dir).pack(anchor="w", pady=(4, 0))

        ttk.Label(path_frame, text="Filename (no extension):").pack(anchor="w", pady=(12, 0))
        self.name_var = tk.StringVar(value=default_name)
        ttk.Entry(path_frame, textvariable=self.name_var).pack(fill=tk.X, pady=(4, 0))

        # Resolution section
        ttk.Label(main_frame, text="Resolution", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(12, 8)
        )

        res_frame = ttk.Frame(main_frame)
        res_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))

        ttk.Label(res_frame, text="Width (px):").grid(row=0, column=0, sticky="e", padx=(0, 6))
        self.width_var = tk.StringVar(value="1920")
        ttk.Entry(res_frame, textvariable=self.width_var, width=10).grid(row=0, column=1, sticky="w")

        ttk.Label(res_frame, text="Height (px):").grid(row=0, column=2, sticky="e", padx=(12, 6))
        self.height_var = tk.StringVar(value="1080")
        ttk.Entry(res_frame, textvariable=self.height_var, width=10).grid(row=0, column=3, sticky="w")

        ttk.Button(res_frame, text="16:9", command=self._set_169).grid(row=0, column=4, padx=(12, 0))
        ttk.Button(res_frame, text="4:3", command=self._set_43).grid(row=0, column=5, padx=(4, 0))
        ttk.Button(res_frame, text="1:1", command=self._set_11).grid(row=0, column=6, padx=(4, 0))

        # Format section
        ttk.Label(main_frame, text="Export Formats", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(12, 8)
        )

        format_frame = ttk.Frame(main_frame)
        format_frame.pack(fill=tk.X, padx=(12, 0), pady=(0, 12))

        self.png_var = tk.BooleanVar(value=True)
        self.pdf_var = tk.BooleanVar(value=True)
        self.csv_var = tk.BooleanVar(value=False)
        self.json_var = tk.BooleanVar(value=False)
        self.fit_csv_var = tk.BooleanVar(value=False)
        self.fit_json_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(format_frame, text="PNG", variable=self.png_var).pack(anchor="w")
        ttk.Checkbutton(format_frame, text="PDF", variable=self.pdf_var).pack(anchor="w", pady=(4, 0))
        if self.peak_finder is not None:
            ttk.Checkbutton(format_frame, text="CSV (Peaks)", variable=self.csv_var).pack(anchor="w", pady=(4, 0))
        if self.fit_states:
            ttk.Checkbutton(format_frame, text="CSV (Fit Results)", variable=self.fit_csv_var).pack(anchor="w", pady=(4, 0))
            ttk.Checkbutton(format_frame, text="JSON (Fit Results)", variable=self.fit_json_var).pack(anchor="w", pady=(4, 0))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(button_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT)

    def _browse_dir(self) -> None:
        """Browse for directory."""
        directory = filedialog.askdirectory(
            initialdir=self.dir_var.get(),
            title="Select Save Directory"
        )
        if directory:
            self.dir_var.set(directory)

    def _set_169(self) -> None:
        """Set 16:9 aspect ratio."""
        width = int(self.width_var.get())
        height = int(width * 9 / 16)
        self.height_var.set(str(height))

    def _set_43(self) -> None:
        """Set 4:3 aspect ratio."""
        width = int(self.width_var.get())
        height = int(width * 3 / 4)
        self.height_var.set(str(height))

    def _set_11(self) -> None:
        """Set 1:1 aspect ratio."""
        width = int(self.width_var.get())
        self.height_var.set(str(width))

    def _save(self) -> None:
        """Perform the save operation."""
        try:
            # Validate inputs
            directory = self.dir_var.get().strip()
            name = self.name_var.get().strip()
            width = int(self.width_var.get())
            height = int(self.height_var.get())

            if not directory or not name:
                messagebox.showerror("Invalid input", "Directory and filename required")
                return

            if width < 100 or height < 100:
                messagebox.showerror("Invalid resolution", "Width and height must be >= 100px")
                return

            if not self.png_var.get() and not self.pdf_var.get() and not self.csv_var.get() and not self.fit_csv_var.get() and not self.fit_json_var.get():
                messagebox.showerror("No format selected", "Select at least one format")
                return

            # Create directory if needed
            os.makedirs(directory, exist_ok=True)

            # Delegate the actual save/export work to SaveManager for
            # screenshots and fit exports. Peak (CSV) export is handled
            # here in the UI layer so SaveManager does not need to
            # inspect feature objects.
            saved_files = self.save_manager.delegate_save(
                root=self.root,
                obj=self.hist,
                directory=directory,
                name=name,
                width=width,
                height=height,
                render_options=self.render_options,
                png=self.png_var.get(),
                pdf=self.pdf_var.get(),
                fit_states=self.fit_states if (self.fit_csv_var.get() or self.fit_json_var.get()) else None,
            )

            # If CSV export of peaks was requested, write peaks here using
            # available peak data. SaveManager exposes `export_peaks_csv`
            # which accepts a plain list of peaks; UI is responsible for
            # assembling that list from feature objects.
            if self.csv_var.get():
                if not self.peak_finder:
                    messagebox.showwarning("No peaks", "No peak data available to export")
                else:
                    try:
                        peaks = None
                        if isinstance(self.peak_finder, (list, tuple)):
                            peaks = list(self.peak_finder)
                        elif hasattr(self.peak_finder, "peaks") and isinstance(getattr(self.peak_finder, "peaks"), (list, tuple)):
                            peaks = list(getattr(self.peak_finder, "peaks"))
                        elif hasattr(self.peak_finder, "get_peaks") and callable(self.peak_finder.get_peaks):
                            peaks = list(self.peak_finder.get_peaks())

                        if peaks:
                            peaks_path = os.path.join(directory, f"{name}_peaks.csv")
                            self.save_manager.export_peaks_csv(peaks, name, peaks_path)
                            saved_files.append(peaks_path)
                        else:
                            messagebox.showwarning("No peaks", "No peak data found to export")
                    except Exception as e:
                        messagebox.showerror("Peaks export failed", f"Error exporting peaks: {e}")

            # Present success
            if saved_files:
                messagebox.showinfo("Success", f"Saved to:\n" + "\n".join(os.path.basename(f) for f in saved_files))
            else:
                messagebox.showinfo("Done", "No files were created")
            self.destroy()

        except ValueError:
            messagebox.showerror("Invalid input", "Width and height must be numbers")
        except Exception as e:
            messagebox.showerror("Save failed", f"Error: {e}")


# Note: callers should import `AdvancedSaveDialog` from this module.

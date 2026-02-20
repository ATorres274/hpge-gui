"""Batch processing tab manager."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any

from tab_managers.tab import Tab
from modules.save_manager import ask_directory, error, info
from modules.save_manager import SaveManager
from modules.error_dispatcher import get_dispatcher, ErrorLevel


class BatchProcessingTab(Tab):
	"""Batch processing tab - auto peak detection and fitting for multiple histograms."""

	name = "Batch Processing"

	def __init__(self) -> None:
		self._export_manager = SaveManager()
		self._dispatcher = get_dispatcher()
		self.root_file = None
		self.histograms: list[tuple[str, Any]] = []  # (path, histogram object)
		self.processing_results: list[dict] = []
		self._listbox: tk.Listbox | None = None
		self._progress_var: tk.StringVar | None = None
		self._status_text: tk.Text | None = None
		self._parent_app = None

	def build_ui(self, app, parent: ttk.Frame) -> None:
		self._parent_app = app

		main_container = ttk.Frame(parent)
		main_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

		# Title
		ttk.Label(
			main_container,
			text="Batch Process Histograms",
			font=("TkDefaultFont", 12, "bold")
		).pack(anchor="w", pady=(0, 8))

		# Controls
		control_frame = ttk.Frame(main_container)
		control_frame.pack(fill=tk.X, pady=(0, 8))

		ttk.Button(
			control_frame,
			text="Scan for Histograms",
			command=self._scan_histograms
		).pack(side=tk.LEFT, padx=(0, 6))

		ttk.Button(
			control_frame,
			text="Process Selected",
			command=self._process_selected
		).pack(side=tk.LEFT, padx=(0, 6))

		ttk.Button(
			control_frame,
			text="Process All",
			command=self._process_all
		).pack(side=tk.LEFT, padx=(0, 6))

		ttk.Button(
			control_frame,
			text="Export Report",
			command=self._export_report
		).pack(side=tk.LEFT)

		# Histogram list
		list_frame = ttk.LabelFrame(main_container, text="Histograms", padding=4)
		list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

		list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
		list_scroll.pack(side=tk.RIGHT, fill=tk.Y)

		self._listbox = tk.Listbox(
			list_frame,
			selectmode=tk.EXTENDED,
			yscrollcommand=list_scroll.set,
			height=10
		)
		self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		list_scroll.config(command=self._listbox.yview)

		# Progress
		progress_frame = ttk.Frame(main_container)
		progress_frame.pack(fill=tk.X, pady=(0, 8))

		self._progress_var = tk.StringVar(value="Ready")
		ttk.Label(progress_frame, textvariable=self._progress_var).pack(anchor="w")

		# Status log
		status_frame = ttk.LabelFrame(main_container, text="Processing Log", padding=4)
		status_frame.pack(fill=tk.BOTH, expand=True)

		status_scroll = ttk.Scrollbar(status_frame, orient=tk.VERTICAL)
		status_scroll.pack(side=tk.RIGHT, fill=tk.Y)

		self._status_text = tk.Text(
			status_frame,
			height=8,
			wrap=tk.WORD,
			yscrollcommand=status_scroll.set
		)
		self._status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		status_scroll.config(command=self._status_text.yview)
		self._status_text.config(state=tk.DISABLED)

	def on_file_opened(self, app, root_file) -> None:
		self.root_file = root_file
		self.histograms = []
		self._update_histogram_list()

	def _scan_histograms(self) -> None:
		"""Scan ROOT file for all histograms."""
		if self.root_file is None:
			messagebox.showwarning("No file", "Please open a ROOT file first")
			return

		self.histograms = []
		self._log("Scanning for histograms...")

		try:
			self._scan_directory(self.root_file, "")
			self._update_histogram_list()
			self._log(f"Found {len(self.histograms)} histogram(s)")
			self._progress_var.set(f"Found {len(self.histograms)} histogram(s)")
		except Exception as e:
			self._log(f"Error scanning: {e}")
			messagebox.showerror("Scan failed", f"Failed to scan histograms:\n{e}")

	def _scan_directory(self, directory, path_prefix: str) -> None:
		"""Recursively scan directory for histograms."""
		keys = directory.GetListOfKeys()
		if not keys:
			return

		for key in keys:
			name = key.GetName()
			class_name = key.GetClassName()
			obj_path = f"{path_prefix}/{name}" if path_prefix else name

			if class_name in ("TDirectory", "TDirectoryFile"):
				subdir = directory.Get(name)
				if subdir:
					self._scan_directory(subdir, obj_path)
			elif class_name.startswith("TH"):
				# This is a histogram
				obj = directory.Get(name)
				if obj:
					self.histograms.append((obj_path, obj))

	def _update_histogram_list(self) -> None:
		"""Update the listbox with found histograms."""
		if self._listbox is None:
			return

		self._listbox.delete(0, tk.END)
		for path, hist in self.histograms:
			display_name = f"{path} ({hist.ClassName()})"
			self._listbox.insert(tk.END, display_name)

	def _process_selected(self) -> None:
		"""Process selected histograms."""
		if not self._listbox:
			return

		selection = self._listbox.curselection()
		if not selection:
			messagebox.showinfo("No selection", "Please select histograms to process")
			return

		selected_hists = [self.histograms[i] for i in selection]
		self._process_histograms(selected_hists)

	def _process_all(self) -> None:
		"""Process all histograms."""
		if not self.histograms:
			messagebox.showinfo("No histograms", "No histograms found. Click 'Scan for Histograms' first.")
			return

		self._process_histograms(self.histograms)

	def _process_histograms(self, histograms: list[tuple[str, Any]]) -> None:
		"""
		Process a list of histograms with peak detection and fitting.

		Args:
			histograms: List of (path, histogram) tuples
		"""
		self.processing_results = []
		total = len(histograms)

		self._log(f"Starting batch processing of {total} histogram(s)...")
		self._progress_var.set(f"Processing 0/{total}")

		try:
			root = self._get_root_module()
			if root is None:
				messagebox.showerror("Error", "ROOT module not available")
				return

			prev_batch = root.gROOT.IsBatch()
			root.gROOT.SetBatch(True)

			try:
				for i, (path, hist) in enumerate(histograms, 1):
					self._log(f"[{i}/{total}] Processing {path}...")
					self._progress_var.set(f"Processing {i}/{total}: {path}")

					result = self._process_single_histogram(root, hist, path)
					self.processing_results.append(result)

					self._log(f"  Peaks: {result['peaks_found']}, Fits: {result['fits_completed']}")

					# Allow UI to update
					if self._parent_app:
						self._parent_app.update_idletasks()

				self._log("Batch processing complete!")
				self._progress_var.set(f"Complete: {total} histogram(s) processed")

				messagebox.showinfo(
					"Processing complete",
					f"Processed {total} histogram(s)\n\nClick 'Export Report' to save results"
				)

			finally:
				root.gROOT.SetBatch(prev_batch)

		except Exception as e:
			self._log(f"Error during batch processing: {e}")
			messagebox.showerror("Processing failed", f"Batch processing failed:\n{e}")

	def _process_single_histogram(
		self,
		root,
		hist,
		path: str
	) -> dict[str, Any]:
		"""
		Process a single histogram: find peaks and fit them.

		Args:
			root: ROOT module
			hist: Histogram object
			path: Path to histogram in ROOT file

		Returns:
			Dictionary with processing results
		"""
		result = {
			"histogram_name": hist.GetName(),
			"histogram_path": path,
			"peaks_found": 0,
			"peaks": [],
			"fits_completed": 0,
			"fits_failed": 0,
			"fit_states": {},
			"status": "completed",
		}

		try:
			# Find peaks using TSpectrum
			spectrum = root.TSpectrum()
			num_peaks = spectrum.Search(hist, 2, "")  # 2 sigma, quiet

			peaks = []
			for i in range(num_peaks):
				energy = spectrum.GetPositionX()[i]
				counts = hist.GetBinContent(hist.FindBin(energy))
				peaks.append({"energy": energy, "counts": counts})

			peaks.sort(key=lambda p: p["energy"])
			result["peaks"] = peaks
			result["peaks_found"] = len(peaks)

			# Fit each peak with Gaussian (10 keV width)
			fit_states = {}
			for peak_idx, peak in enumerate(peaks):
				energy = peak["energy"]
				width = 10.0  # Fixed 10 keV width

				try:
					fit_result = self._fit_peak(root, hist, energy, width, peak_idx)
					if fit_result and "error" not in fit_result.get("cached_results", {}):
						fit_states[peak_idx] = fit_result
						result["fits_completed"] += 1
					else:
						result["fits_failed"] += 1
				except Exception:
					result["fits_failed"] += 1

			result["fit_states"] = fit_states

		except Exception as e:
			result["status"] = f"failed: {e}"

		return result

	def _fit_peak(
		self,
		root,
		hist,
		energy: float,
		width: float,
		peak_idx: int
	) -> dict | None:
		"""
		Fit a single peak with Gaussian function.

		Args:
			root: ROOT module
			hist: Histogram object
			energy: Peak energy in keV
			width: Fit width in keV
			peak_idx: Peak index

		Returns:
			Fit state dictionary with cached results
		"""
		try:
			xmin = energy - width / 2
			xmax = energy + width / 2

			fit_func = "gaus"
			fit_name = f"fit_{fit_func}_{peak_idx}"

			# Perform fit
			with open(os.devnull, "w") as devnull:
				from contextlib import redirect_stdout, redirect_stderr

				with redirect_stdout(devnull), redirect_stderr(devnull):
					fit_result = hist.Fit(fit_func, "SQ", "", xmin, xmax)

			# Cache results immediately
			if fit_result and fit_result.Status() == 0:
				num_params = len(fit_result.Parameters())
				cached_results = {
					"chi2": float(fit_result.Chi2()),
					"ndf": int(fit_result.Ndf()),
					"status": int(fit_result.Status()),
					"parameters": list(fit_result.Parameters()),
					"errors": [float(fit_result.ParError(i)) for i in range(num_params)],
				}

				# Store in fit_state format
				fit_state = {
					"tab_id": peak_idx,
					"fit_func_var": type("StringVar", (), {"get": lambda: fit_func})(),
					"energy_var": type("StringVar", (), {"get": lambda: str(energy)})(),
					"width_var": type("StringVar", (), {"get": lambda: str(width)})(),
					"cached_results": cached_results,
					"peak_idx": peak_idx,
				}

				return fit_state
			return {
				"tab_id": peak_idx,
				"cached_results": {"error": "Fit failed"},
			}

		except Exception:
			return None

	def _export_report(self) -> None:
		"""Export batch processing report."""
		if not self.processing_results:
			messagebox.showinfo("No data", "No processing results to export")
			return
		output_dir = ask_directory(title="Select Output Directory")
		if not output_dir:
			return
		try:
			self._export_manager.create_batch_report(self.processing_results, output_dir=output_dir)
			info(
				"Batch report created",
				f"Batch processing report saved to:\n{output_dir}\n\n"
				f"Processed {len(self.processing_results)} histogram(s)"
			)
		except Exception as exc:
			error("Report failed", f"Failed to create batch report:\n{exc}")

	def _log(self, message: str) -> None:
		"""Add message to status log."""
		if not self._status_text:
			return

		self._status_text.config(state=tk.NORMAL)
		self._status_text.insert(tk.END, message + "\n")
		self._status_text.see(tk.END)
		self._status_text.config(state=tk.DISABLED)

	def _get_root_module(self):
		"""Get ROOT module."""
		if self._parent_app:
			root = getattr(self._parent_app, "ROOT", None)
			if root is not None:
				return root
		try:
			import ROOT
			return ROOT
		except Exception:
			return None


__all__ = ["BatchProcessingFeature"]

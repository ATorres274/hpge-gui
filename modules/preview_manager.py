from __future__ import annotations

import tkinter as tk
from weakref import WeakKeyDictionary
from typing import Optional

from features.renderer_feature import RendererFeature


class HistogramRenderer:
    """Combined preview manager that delegates heavy rendering to RendererFeature.

    This class provides the async/coalesced preview rendering into a Tk
    `Label` widget as well as file-based render helpers that call the
    underlying `RendererFeature`. Keeping this logic in a single module
    helps organize preview responsibilities.
    """

    def __init__(self) -> None:
        self._feature = RendererFeature()
        self._pending: WeakKeyDictionary[tk.Label, dict] = WeakKeyDictionary()
        self._render_counter = 0

    def __del__(self) -> None:
        try:
            self._feature.cleanup()
        except Exception:
            pass

    def render_into_label(self, root, hist, label: tk.Label, options: dict | None = None) -> None:
        label.update_idletasks()

        # If explicit target size provided in options, use it. Otherwise
        # fall back to label geometry with reasonable defaults.
        target_w = None
        target_h = None
        if options:
            try:
                target_w = int(options.get("target_width"))
            except Exception:
                target_w = None
            try:
                target_h = int(options.get("target_height"))
            except Exception:
                target_h = None

        if target_w is not None and target_h is not None:
            # Honor a priority hint if provided: 'height' or 'width'. When
            # prioritizing height we choose the requested height and derive
            # width from a sensible aspect ratio. Clamp to the actual label
            # geometry when available so the image cannot force the window
            # to expand.
            priority = None
            if options:
                priority = options.get("priority")

            width = target_w
            height = target_h

            try:
                lbl_w = label.winfo_width() or 0
                lbl_h = label.winfo_height() or 0
            except Exception:
                lbl_w = lbl_h = 0

            # If priority is 'height', derive width from height (16:9),
            # but do not exceed the label width if available.
            if priority == "height":
                try:
                    derived_w = int(height * 16 / 9)
                    if lbl_w and derived_w > lbl_w:
                        derived_w = lbl_w
                    width = max(120, derived_w)
                except Exception:
                    pass

            # If priority is 'width', derive height from width (9:16)
            if priority == "width":
                try:
                    derived_h = int(width * 9 / 16)
                    if lbl_h and derived_h > lbl_h:
                        derived_h = lbl_h
                    height = max(80, derived_h)
                except Exception:
                    pass

            # Finally, clamp to label geometry if it exists to avoid
            # the image requesting a larger widget size than displayed.
            try:
                if lbl_w and width > lbl_w:
                    width = lbl_w
                if lbl_h and height > lbl_h:
                    height = lbl_h
            except Exception:
                pass
        else:
            width = label.winfo_width() or 0
            height = label.winfo_height() or 0

            if width < 200 or height < 200:
                try:
                    parent = label.winfo_toplevel()
                    parent_width = parent.winfo_width() or 900
                    width = max(parent_width - 32, 800)
                    width = min(width, 2200)
                    height = int(width * 9 / 16)
                except Exception:
                    width = width or 400
                    height = height or 240

        render_options = self._normalize_options(options)

        image_path = self._feature.render_to_temp_image(root, hist, int(width), int(height), render_options)

        try:
            image_ref = tk.PhotoImage(file=image_path)
            label.configure(image=image_ref)
            label.image = image_ref
        except tk.TclError:
            pass
        finally:
            try:
                self._feature.release_temp_image(image_path)
            except Exception:
                pass

    def render_into_label_async(
        self,
        root,
        hist,
        label: tk.Label,
        options: dict | None = None,
        delay_ms: int = 0,
    ) -> None:
        pending = self._pending.get(label)
        if pending and pending.get("id") is not None:
            try:
                label.after_cancel(pending["id"])
            except Exception:
                pass

        self._render_counter += 1
        token = self._render_counter
        self._pending[label] = {"id": None, "token": token}

        def _run() -> None:
            current = self._pending.get(label)
            if not current or current.get("token") != token:
                return
            current["id"] = None
            try:
                self.render_into_label(root, hist, label, options)
            except Exception:
                pass

        try:
            self._pending[label]["id"] = label.after(delay_ms, _run)
        except Exception:
            pass

    def save_to_file(self, root, hist, path: str, width: int, height: int, options: dict | None = None) -> None:
        render_options = self._normalize_options(options)
        self._feature.render_to_file(root, hist, path, int(width), int(height), render_options)

    def render_to_temp_image(self, root, hist, width: int, height: int, options: dict | None = None) -> str:
        return self._feature.render_to_temp_image(root, hist, width, height, options)

    def render_to_temp_pdf(self, root, hist, width: int, height: int, options: dict | None = None) -> str:
        return self._feature.render_to_temp_pdf(root, hist, width, height, options)

    def release_temp_image(self, path: str) -> None:
        try:
            self._feature.release_temp_image(path)
        except Exception:
            pass

    def cleanup(self) -> None:
        try:
            self._feature.cleanup()
        except Exception:
            pass

    @staticmethod
    def _normalize_options(options: dict | None) -> dict:
        if not options:
            return {}

        normalized: dict = {}
        if options.get("logx"):
            normalized["logx"] = True
        if options.get("logy"):
            normalized["logy"] = True
        if options.get("logz"):
            normalized["logz"] = True

        normalized["show_markers"] = options.get("show_markers", True)

        xmin = options.get("xmin")
        xmax = options.get("xmax")
        if xmin is not None and xmax is not None:
            normalized["xrange"] = (xmin, xmax)

        ymin = options.get("ymin")
        ymax = options.get("ymax")
        if ymin is not None and ymax is not None:
            normalized["yrange"] = (ymin, ymax)

        if options.get("title"):
            normalized["title"] = options["title"]
        if options.get("xtitle"):
            normalized["xtitle"] = options["xtitle"]
        if options.get("ytitle"):
            normalized["ytitle"] = options["ytitle"]

        if options.get("markers"):
            normalized["markers"] = options["markers"]

        return normalized

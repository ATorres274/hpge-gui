from __future__ import annotations

import os
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from array import array

from features.feature import Feature


class RootRenderer:
    """Centralized ROOT rendering with output suppression.

    This implementation was previously located in `modules/root_renderer.py`.
    The code is retained here inside the `features` layer so features own
    the heavy ROOT interactions while modules call into the feature.
    """

    def __init__(self) -> None:
        self._temp_images: list[str] = []

    def render_to_file(
        self,
        root,
        obj,
        filepath: str,
        width: int,
        height: int,
        options: dict | None = None,
    ) -> None:
        if options is None:
            options = {}

        root.gROOT.SetBatch(True)
        try:
            with open(os.devnull, "w") as devnull:
                with redirect_stdout(devnull), redirect_stderr(devnull):
                    old_stdout = os.dup(1)
                    old_stderr = os.dup(2)
                    try:
                        os.dup2(devnull.fileno(), 1)
                        os.dup2(devnull.fileno(), 2)

                        canvas = root.TCanvas("_pyhpge_canvas", "Render", int(width), int(height))
                        canvas.cd()

                        render_obj = obj
                        if hasattr(obj, "Clone"):
                            try:
                                render_obj = obj.Clone(f"{obj.GetName()}_render")
                                if hasattr(render_obj, "SetDirectory"):
                                    render_obj.SetDirectory(0)
                            except Exception:
                                render_obj = obj

                        if not options.get("show_markers", True):
                            if hasattr(render_obj, "GetListOfFunctions"):
                                func_list = render_obj.GetListOfFunctions()
                                to_remove = []
                                for i in range(func_list.GetSize()):
                                    obj_at_i = func_list.At(i)
                                    if obj_at_i and obj_at_i.ClassName() == "TPolyMarker":
                                        to_remove.append(obj_at_i)
                                for obj_to_remove in to_remove:
                                    func_list.Remove(obj_to_remove)

                        if options.get("clear_functions", False):
                            if hasattr(render_obj, "GetListOfFunctions"):
                                fit_list = render_obj.GetListOfFunctions()
                                while fit_list.GetSize() > 1:
                                    func = fit_list.At(0)
                                    fit_list.Remove(func)

                        # When a specific TF1 is provided, clear ALL attached
                        # functions from the clone and draw only that one.
                        # This ensures each fit preview shows its own curve.
                        fit_func_obj = options.get("fit_func_obj")
                        if fit_func_obj is not None:
                            if hasattr(render_obj, "GetListOfFunctions"):
                                try:
                                    fl = render_obj.GetListOfFunctions()
                                    fl.Clear()
                                except Exception:
                                    pass

                        try:
                            canvas.SetDPI(150)
                        except AttributeError:
                            pass

                        self._apply_options(root, canvas, render_obj, options)

                        render_obj.Draw()

                        # Draw the per-fit TF1 curve after the histogram.
                        if fit_func_obj is not None:
                            try:
                                fit_func_obj.Draw("same")
                            except Exception:
                                pass

                        try:
                            show_markers = options.get("show_markers", True)
                            if show_markers and hasattr(render_obj, "FindBin"):
                                def _draw_markers(marker_list, style, size, color):
                                    if not marker_list:
                                        return
                                    xs = array("d", [float(m) for m in marker_list])
                                    ys = array("d", [])
                                    for val in xs:
                                        try:
                                            bin_idx = render_obj.FindBin(val)
                                            ys.append(float(render_obj.GetBinContent(bin_idx)))
                                        except Exception:
                                            ys.append(0.0)
                                    try:
                                        poly = root.TPolyMarker(len(xs), xs, ys)
                                        try:
                                            poly.SetMarkerStyle(style)
                                            poly.SetMarkerSize(size)
                                            try:
                                                poly.SetMarkerColor(color)
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                                        try:
                                            poly.Draw("P same")
                                        except Exception:
                                            pass
                                    except Exception:
                                        pass

                                # Automatic peaks: red five-pointed star (style 29)
                                _draw_markers(
                                    options.get("markers"), style=29, size=3, color=2
                                )
                                # Manual peaks: blue open circle (style 24)
                                _draw_markers(
                                    options.get("manual_markers"), style=24, size=2, color=4
                                )
                                try:
                                    canvas.Modified()
                                    canvas.Update()
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        # Optional TPaveText overlay (fit results on the canvas).
                        # Placed in the top-right corner to avoid the peak data.
                        pavetext = options.get("pavetext")
                        if pavetext:
                            try:
                                pave = root.TPaveText(0.52, 0.60, 0.97, 0.97, "NDC")
                                pave.SetFillColor(0)
                                pave.SetFillStyle(1001)
                                pave.SetFillColorAlpha(0, 0.75)  # semi-transparent
                                pave.SetBorderSize(1)
                                pave.SetTextAlign(12)
                                pave.SetTextFont(42)
                                pave.SetTextSize(0.042)
                                for line in str(pavetext).split("\n"):
                                    pave.AddText(line if line.strip() else " ")
                                pave.Draw()
                                try:
                                    canvas.Modified()
                                    canvas.Update()
                                except Exception:
                                    pass
                            except Exception:
                                pass

                        canvas.Print(filepath)
                        if render_obj is not obj:
                            try:
                                render_obj.Delete()
                            except Exception:
                                pass
                    finally:
                        try:
                            canvas.Close()
                        except Exception:
                            pass
                        os.dup2(old_stdout, 1)
                        os.dup2(old_stderr, 2)
                        os.close(old_stdout)
                        os.close(old_stderr)
        finally:
            root.gROOT.SetBatch(False)

    def render_to_temp_image(
        self,
        root,
        obj,
        width: int,
        height: int,
        options: dict | None = None,
    ) -> str:
        if options is None:
            options = {}

        with open(os.devnull, "w") as devnull:
            with redirect_stdout(devnull), redirect_stderr(devnull):
                fd, filepath = tempfile.mkstemp(prefix="pyhpge_render_", suffix=".png")
                os.close(fd)

        self._temp_images.append(filepath)
        self.render_to_file(root, obj, filepath, width, height, options)
        return filepath

    def release_temp_image(self, filepath: str) -> None:
        try:
            if filepath in self._temp_images:
                self._temp_images.remove(filepath)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

    def _apply_options(self, root, canvas, obj, options: dict) -> None:
        # Suppress the ROOT stats box globally for this render.
        try:
            root.gStyle.SetOptStat(0)
        except Exception:
            pass
        try:
            obj.SetStats(0)
        except Exception:
            pass

        # Apply default tight margins so exported images don't have
        # excessive white space around axis labels and titles.
        # Users can override these via options keys if needed.
        try:
            left = float(options.get("left_margin", 0.08))
        except Exception:
            left = 0.08
        try:
            right = float(options.get("right_margin", 0.02))
        except Exception:
            right = 0.02
        try:
            top = float(options.get("top_margin", 0.08))
        except Exception:
            top = 0.08
        try:
            bottom = float(options.get("bottom_margin", 0.12))
        except Exception:
            bottom = 0.12

        try:
            canvas.SetLeftMargin(left)
            canvas.SetRightMargin(right)
            canvas.SetTopMargin(top)
            canvas.SetBottomMargin(bottom)
        except Exception:
            pass

        # Try to remove canvas/pad borders and apply margins at the pad level
        try:
            try:
                canvas.SetFillColor(0)
                canvas.SetBorderMode(0)
            except Exception:
                pass

            try:
                # ensure we're in the canvas' pad and set pad margins too
                canvas.cd()
                pad = None
                try:
                    pad = canvas.GetPad()
                except Exception:
                    try:
                        pad = canvas.GetPad(0)
                    except Exception:
                        pad = None

                if pad is not None:
                    try:
                        pad.SetLeftMargin(left)
                        pad.SetRightMargin(right)
                        pad.SetTopMargin(top)
                        pad.SetBottomMargin(bottom)
                    except Exception:
                        pass

                    try:
                        pad.SetFrameFillColor(0)
                        pad.SetBorderMode(0)
                        pad.SetFrameBorderMode(0)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        if options.get("logx"):
            canvas.SetLogx(1)
        if options.get("logy"):
            canvas.SetLogy(1)
        if options.get("logz"):
            canvas.SetLogz(1)

        if not hasattr(obj, "GetXaxis"):
            return

        xaxis = obj.GetXaxis()
        yaxis = obj.GetYaxis() if hasattr(obj, "GetYaxis") else None

        xrange = options.get("xrange")
        if xrange and xrange[0] is not None and xrange[1] is not None:
            xaxis.SetRangeUser(xrange[0], xrange[1])

            # Auto-fit Y range to the visible window so the peak fills the
            # preview vertically.  Only done when xrange is explicitly set
            # (i.e. a zoomed fit preview) and no explicit yrange was supplied.
            if yaxis and not options.get("yrange"):
                try:
                    b1 = obj.FindBin(float(xrange[0]))
                    b2 = obj.FindBin(float(xrange[1]))
                    y_max = 0.0
                    y_min = float("inf")
                    for b in range(max(1, b1), b2 + 1):
                        val = float(obj.GetBinContent(b))
                        if val > y_max:
                            y_max = val
                        if val > 0 and val < y_min:
                            y_min = val
                    if y_max > 0:
                        logy = options.get("logy", False)
                        if logy:
                            # In log scale keep a one-decade margin below and
                            # 30 % headroom above so axis labels don't clip.
                            lo = max(y_min * 0.5, 0.5)
                            hi = y_max * 1.5
                        else:
                            lo = 0.0
                            hi = y_max * 1.15
                        yaxis.SetRangeUser(lo, hi)
                except Exception:
                    pass

        if yaxis:
            yrange = options.get("yrange")
            if yrange and yrange[0] is not None and yrange[1] is not None:
                yaxis.SetRangeUser(yrange[0], yrange[1])

        if options.get("title"):
            obj.SetTitle(options["title"])
        if options.get("xtitle"):
            xaxis.SetTitle(options["xtitle"])
        if yaxis and options.get("ytitle"):
            yaxis.SetTitle(options["ytitle"])

    def cleanup(self) -> None:
        for filepath in self._temp_images:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
        self._temp_images.clear()


class RendererFeature(Feature):
    """Feature wrapper around `RootRenderer` to expose rendering APIs to modules.

    Modules (preview managers, save manager, etc.) should use this feature
    rather than depending directly on `RootRenderer` so rendering is a
    well-defined feature responsibility.
    """
    name = "Renderer"

    def __init__(self) -> None:
        self._renderer = RootRenderer()

    def render_to_file(self, root, obj, filepath: str, width: int, height: int, options: dict | None = None) -> None:
        return self._renderer.render_to_file(root, obj, filepath, width, height, options)

    def render_to_temp_image(self, root, obj, width: int, height: int, options: dict | None = None) -> str:
        return self._renderer.render_to_temp_image(root, obj, width, height, options)

    def render_to_temp_pdf(self, root, obj, width: int, height: int, options: dict | None = None) -> str:
        fd, filepath = tempfile.mkstemp(prefix="pyhpge_render_", suffix=".pdf")
        os.close(fd)
        try:
            self._renderer.render_to_file(root, obj, filepath, width, height, options)
            return filepath
        except Exception:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            raise

    def release_temp_image(self, filepath: str) -> None:
        return self._renderer.release_temp_image(filepath)

    def cleanup(self) -> None:
        return self._renderer.cleanup()

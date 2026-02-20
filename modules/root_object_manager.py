from __future__ import annotations

import os
import signal
import subprocess


class RootObjectManager:
    """Manage subprocesses that display ROOT objects."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = base_dir or os.path.dirname(__file__)
        self._processes: list[subprocess.Popen] = []

    def open_object(self, root_path: str, obj_path: str) -> None:
        """Open a ROOT object in a subprocess and track it for cleanup."""
        script = f"""
import sys
sys.path.insert(0, r'{self._base_dir}')
try:
    import ROOT
    file = ROOT.TFile.Open(r'{root_path}')
    obj = file.Get(r'{obj_path}')
    if obj:
        canvas = ROOT.TCanvas('c_canvas', 'Histogram', 900, 700)
        obj.Draw()
        canvas.Update()
        ROOT.gApplication.Run(True)
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
"""
        try:
            process = subprocess.Popen(
                ["python", "-c", script],
                start_new_session=True,
            )
            self._processes.append(process)
        except Exception:
            pass

    def close_all(self) -> None:
        """Terminate any subprocesses opened for ROOT object display."""
        remaining: list[subprocess.Popen] = []
        for process in self._processes:
            if process.poll() is not None:
                continue
            try:
                if process.pid:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except Exception:
                    process.kill()
            except Exception:
                remaining.append(process)
        self._processes = remaining

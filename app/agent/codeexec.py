"""Subprocess Python execution for tutor compute/plot tools.

One runner, two permission tiers enforced by the CALLERS, not prose:
- run_code: stdout only (collect_plot=False).
- plot_chart: stdout + output.png collected as a data URL (Agg backend).

Posture (single-user local box, stated not implied): wall-clock timeout
with kill, stdout/stderr caps, fresh temp cwd per call. No import or
network restrictions — timeouts and caps are the sandbox.
"""

from __future__ import annotations

import asyncio
import base64
import sys
import tempfile
from pathlib import Path

RUN_TIMEOUT = 30.0
OUT_MAX = 20_000  # chars per stream; beyond truncates with a flag
PLOT_FILE = "output.png"
PLOT_BYTES_MAX = 2_000_000


async def run_python(
    code: str, *, timeout: float = RUN_TIMEOUT, collect_plot: bool = False
) -> dict:
    """Execute code in a child venv python. Never raises — failures,
    timeouts, and oversize outputs come back as data for the model."""
    if not code.strip():
        return {"error": "code must be non-empty"}
    timeout = max(5.0, min(120.0, float(timeout or RUN_TIMEOUT)))
    prelude = ""
    if collect_plot:
        prelude = "import matplotlib as _mpl; _mpl.use('Agg');\n"
    with tempfile.TemporaryDirectory(prefix="kbexec_") as td:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", prelude + code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=td,
            )
            try:
                raw_out, raw_err = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.communicate()
                return {"stdout": "", "stderr": "",
                        "timed_out": True, "truncated": False,
                        "error": f"timeout after {timeout:g}s — simplify"}
        except OSError as e:
            return {"error": f"spawn failed: {e}"}
        stdout = raw_out.decode("utf-8", "replace")
        stderr = raw_err.decode("utf-8", "replace")
        truncated = False
        if len(stdout) > OUT_MAX:
            stdout = stdout[:OUT_MAX]
            truncated = True
        if len(stderr) > OUT_MAX:
            stderr = stderr[:OUT_MAX]
            truncated = True
        out: dict = {"stdout": stdout, "stderr": stderr,
                     "timed_out": False, "truncated": truncated}
        if collect_plot:
            plot = Path(td) / PLOT_FILE
            if not plot.exists():
                out["error"] = "no output.png saved — save the figure to output.png"
                return out
            data = plot.read_bytes()
            if len(data) > PLOT_BYTES_MAX:
                out["error"] = f"output.png too large ({len(data)} bytes) — lower dpi"
                return out
            out["images"] = [
                "data:image/png;base64," + base64.b64encode(data).decode()
            ]
        return out

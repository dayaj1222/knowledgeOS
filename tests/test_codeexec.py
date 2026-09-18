"""Code tiers: compute (stdout), plot (PNG), demo (sandboxed HTML).

Contract: never raises — timeouts, caps, and violations come back as data.
Tiers separated by tools, not prose: run_code (no files/images), plot_chart
(output.png only), show_demo (self-contained HTML, no network).
"""

import asyncio

from app.agent import cards
from app.agent.codeexec import run_python
from app.agent.tutor_tools import plot_chart, run_code, show_demo


def run(coro):
    return asyncio.run(coro)


def test_compute_stdout_and_scipy():
    out = run(run_python("from scipy.stats import t\nprint(t.ppf(0.975, 14))"))
    assert out["timed_out"] is False
    assert abs(float(out["stdout"]) - 2.1448) < 1e-3
    assert out["stderr"] == ""


def test_compute_error_surfaced():
    out = run(run_python("1/0"))
    assert "ZeroDivisionError" in out["stderr"]


def test_compute_timeout_kills():
    out = run(run_python("import time; time.sleep(30)", timeout=5.0))
    assert out["timed_out"] is True
    assert "timeout" in out["error"]


def test_compute_output_capped():
    out = run(run_python("print('x' * 50000)"))
    assert out["truncated"] is True
    assert len(out["stdout"]) == 20_000


def test_plot_collects_png():
    out = run(run_python(
        "import matplotlib.pyplot as plt\n"
        "plt.plot([0, 1], [0, 1])\n"
        "plt.savefig('output.png')\n", collect_plot=True))
    assert out.get("images") and out["images"][0].startswith("data:image/png;base64,")
    assert out["timed_out"] is False


def test_plot_missing_file_errors():
    out = run(run_python("print('no figure')", collect_plot=True))
    assert "output.png" in out["error"]


def test_run_code_tool_no_plot():
    out = run(run_code(None, 1, {"code": "print(17*23)"}))
    assert out["stdout"].strip() == "391"
    assert "images" not in out


def test_plot_chart_tool_builds_figure_payload():
    out = run(plot_chart(None, 1, {
        "code": "import matplotlib.pyplot as plt\nplt.plot([0,1])\nplt.savefig('output.png')\n",
        "title": "Line",
    }))
    assert out["title"] == "Line"
    assert out["image"].startswith("data:image/png;base64,")


def test_show_demo_rejects_oversize_and_external():
    big = show_demo(None, 1, {"html": "<p>" + "x" * 30_001})
    assert "exceeds" in big["error"]
    net = show_demo(None, 1, {"html": '<script src="https://cdn/x.js"></script>'})
    assert "external" in net["error"]
    ok = show_demo(None, 1, {"html": "<canvas></canvas>", "title": "D"})
    assert ok["title"] == "D" and "<canvas>" in ok["html"]


def test_demo_and_figure_cards_validate_and_slim():
    html = "<p>demo</p>"
    cards.validate("demo", {"html": html})
    slimmed = cards.slim("demo", {"html": html, "title": "T", "height": 5000})
    assert slimmed["height"] == 800 and slimmed["html"] == html
    img = "data:image/png;base64,AAA"
    cards.validate("figure", {"image": img})
    slimmed = cards.slim("figure", {"image": img, "title": "F", "stdout": "ok"})
    assert slimmed["image"] == img and slimmed["stdout"] == "ok"

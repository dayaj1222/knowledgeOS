"""Safe, local visual and computation tools used by the tutor registry."""


def show_demo(db, user_id: int, args: dict) -> dict:
    """Validate a self-contained interactive demo for a sandboxed card."""
    from .cards import DEMO_HTML_MAX

    html = str(args.get("html", ""))
    if not html.strip():
        return {"error": "html must be a non-empty self-contained document"}
    if len(html) > DEMO_HTML_MAX:
        return {"error": f"html exceeds {DEMO_HTML_MAX} chars ({len(html)}) — simplify"}
    low = html.lower()
    if "http://" in low or "https://" in low:
        return {"error": "external URLs forbidden — inline all CSS/JS, no CDNs"}
    return {
        "title": str(args.get("title", "Interactive demo"))[:120],
        "html": html,
        "height": args.get("height", 420),
    }


async def run_code(db, user_id: int, args: dict) -> dict:
    """Run a numeric calculation in the isolated local Python sandbox."""
    from .codeexec import run_python

    code = str(args.get("code", ""))
    try:
        timeout = float(args.get("timeout") or 30.0)
    except (TypeError, ValueError):
        timeout = 30.0
    return await run_python(code, timeout=timeout, collect_plot=False)


async def plot_chart(db, user_id: int, args: dict) -> dict:
    """Run chart code in the isolated sandbox and return one inline image."""
    from .codeexec import run_python

    code = str(args.get("code", ""))
    try:
        timeout = float(args.get("timeout") or 30.0)
    except (TypeError, ValueError):
        timeout = 30.0
    out = await run_python(code, timeout=timeout, collect_plot=True)
    if out.get("error") or not out.get("images"):
        return out
    return {
        "title": str(args.get("title", "Figure"))[:120],
        "image": out["images"][0],
        "stdout": out.get("stdout", ""),
    }

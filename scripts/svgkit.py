"""Shared SVG helpers. Standard library only.

generate_stats.py imports this and runs in CI, so nothing here may pull a
dependency. base64 and pathlib are stdlib; that is the whole toolkit.
"""
import base64
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"

# One fill colour, two themes. Per-character colouring is what makes most ASCII
# portraits look like static, so the palette is deliberately this small.
LIGHT = {"fg": "#1f2328", "dim": "#59636e", "faint": "#d1d9e0"}
DARK = {"fg": "#e6edf3", "dim": "#7d8590", "faint": "#30363d"}


def font_face(name: str, family: str = "JBM", weight: int = 400) -> str:
    """Inline a woff2 subset as a data: URI.

    An external font URL cannot work: these SVGs load through an <img> tag and
    browsers refuse subresource fetches for image documents. A data: URI does.
    """
    b64 = base64.b64encode((FONTS / f"{name}.woff2").read_bytes()).decode()
    return (
        f"@font-face{{font-family:'{family}';font-weight:{weight};"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
    )


def theme_vars() -> str:
    """Light by default, dark via media query.

    GitHub strips <style> from README *markdown*, but an SVG is a separate
    document that never passes through that sanitiser, so this works.

    Ceiling: prefers-color-scheme follows the visitor's OS, not their GitHub
    theme setting. The <picture> approach has the identical limitation.
    """
    light = ";".join(f"--{k}:{v}" for k, v in LIGHT.items())
    dark = ";".join(f"--{k}:{v}" for k, v in DARK.items())
    return f":root{{{light}}}@media (prefers-color-scheme:dark){{:root{{{dark}}}}}"


def svg(width: float, height: float, style: str, body: str, label: str) -> str:
    """Wrap a document. aria-label carries the meaning; these are <img> tags."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">'
        f"<style>{style}</style>{body}</svg>"
    )


def text(x: float, y: float, s: str, cls: str = "", size: float = 0, extra: str = "") -> str:
    attrs = f'x="{x}" y="{y}"'
    if cls:
        attrs += f' class="{cls}"'
    if size:
        attrs += f' font-size="{size}"'
    if extra:
        attrs += f" {extra}"
    return f"<text {attrs}>{escape(s)}</text>"


def write(path: Path, content: str) -> None:
    """Parse before writing, then write LF.

    An unescaped '&' anywhere in an SVG fails the whole document, and the browser
    reports it as a 0x0 image rather than an error -- so it ships looking fine in
    a diff and broken on the page. Parsing here catches it at generation time for
    every generator, instead of relying on each one to escape correctly.

    LF always: the nightly runner writes LF, and a CRLF local checkout would make
    git report every generated file as modified on every run.
    """
    # XXE and billion-laughs both require a DTD, and these generators never emit
    # one. Rejecting it outright closes both without pulling in defusedxml, which
    # would break the stdlib-only constraint generate_stats.py runs under in CI.
    head = content.lstrip()[:2048].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise SystemExit(f"{path.name}: unexpected DTD in generated output")
    try:
        ElementTree.fromstring(content)
    except ElementTree.ParseError as e:
        raise SystemExit(f"{path.name}: invalid XML at {e.position} -- {e}") from e
    path.write_text(content, encoding="utf-8", newline="\n")
    print(f"  {path.name:<16} {len(content) / 1024:6.1f} KB")

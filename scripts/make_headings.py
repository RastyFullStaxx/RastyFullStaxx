"""Section headings as SVG -- the only way to put our own typeface on a heading.

Tradeoff, stated plainly: image headings have no anchor links, so GitHub's README
outline goes empty. The aria-label carries the word for screen readers.

Run once:  python scripts/make_headings.py
"""
from svgkit import ROOT, font_face, svg, theme_vars, write

W, H = 760, 34
BASE = 23          # text baseline
SIZE = 15
TRACK = 3.2        # letter-spacing; the label is small, it needs the air

HEADINGS = ["stats", "stack", "work"]


def build(word: str) -> str:
    style = (
        font_face("head", weight=700)
        + theme_vars()
        + f"text{{font-family:'JBM',monospace;font-weight:700;font-size:{SIZE}px;"
        f"letter-spacing:{TRACK}px;fill:var(--dim)}}"
        + "line{stroke:var(--faint);stroke-width:1}"
    )
    # Advance is 0.600 em, plus tracking on every character.
    label_w = len(word) * (SIZE * 0.600 + TRACK)
    rule_x = label_w + 16
    body = (
        f'<text x="0" y="{BASE}">{word}</text>'
        f'<line x1="{rule_x}" y1="{BASE - 5}" x2="{W}" y2="{BASE - 5}"/>'
    )
    return svg(W, H, style, body, word)


def main() -> None:
    print("headings")
    for word in HEADINGS:
        write(ROOT / f"h-{word}.svg", build(word))


if __name__ == "__main__":
    main()

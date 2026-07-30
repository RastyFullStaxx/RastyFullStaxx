"""Section headings as SVG -- the only way to put our own typeface on a heading.

Tradeoff, stated plainly: image headings have no anchor links, so GitHub's README
outline goes empty. The aria-label carries the word for screen readers.

These deliberately do NOT use the shared W/PAD from svgkit. The dividers span the
full README column and are not inset with the data graphics: they are the rule
everything else sits under, so they stay full width no matter what the charts do.

Run once:  python scripts/make_headings.py
"""
from svgkit import ROOT, font_face, svg, theme_vars, write

W, H = 760, 34     # full column width, independent of the chart canvas
BASE = 23          # text baseline
SIZE = 15
TRACK = 3.2        # letter-spacing; the label is small, it needs the air
GAP = 16           # space between the label and each rule

HEADINGS = ["about", "stats", "projects", "stack", "work"]


def build(word: str) -> str:
    style = (
        font_face("head", weight=700)
        + theme_vars()
        + f"text{{font-family:'JBM',monospace;font-weight:700;font-size:{SIZE}px;"
        f"letter-spacing:{TRACK}px;fill:var(--dim)}}"
        + "line{stroke:var(--faint);stroke-width:1}"
    )
    # Advance is 0.600 em, plus tracking on every character. letter-spacing also
    # adds a trailing gap after the last glyph, so the visual centre sits half a
    # track left of the geometric one.
    label_w = len(word) * (SIZE * 0.600 + TRACK)
    mid = W / 2
    left_end = mid - label_w / 2 - GAP
    right_start = mid + label_w / 2 + GAP
    y = BASE - 5
    body = (
        f'<line x1="0" y1="{y}" x2="{left_end:.1f}" y2="{y}"/>'
        f'<text x="{mid - TRACK / 2:.1f}" y="{BASE}" text-anchor="middle">{word}</text>'
        f'<line x1="{right_start:.1f}" y1="{y}" x2="{W}" y2="{y}"/>'
    )
    return svg(W, H, style, body, word, pad=0)


def main() -> None:
    print("headings")
    for word in HEADINGS:
        write(ROOT / f"h-{word}.svg", build(word))


if __name__ == "__main__":
    main()

"""ASCII self-portrait as a self-typing SVG.

    pip install pillow numpy opencv-python-headless rembg onnxruntime
    python scripts/make_portrait.py                    # defaults
    python scripts/make_portrait.py --gamma 2.0        # darker
    python scripts/make_portrait.py --preview          # .txt, no SVG, fast

The first run downloads a ~176 MB background-removal model. Once, then cached.

Expect to run this several times. The gamma is the knob that matters: the source
photo is lit flat and frontal, which is the pipeline's worst input, and the
darkening curve is what makes brows, hair edges and the jawline survive.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from svgkit import ROOT, font_face, svg, theme_vars, write

# --- the grid. these are load-bearing; see the design spec -----------------
COLS = 90                 # below ~88 the face muddies
DISPLAY_W = 460           # much wider and the block dominates the page
FONT_SIZE = 12.9
CHAR_W = 7.74             # exactly 0.600 em
LINE_H = CHAR_W / 0.48    # mono glyphs are ~2x tall as wide
RAMP = " .`:-=+*cs#%@"    # leading space clears the cut-out to nothing

# --- tuning ---------------------------------------------------------------
# Tuned against photo/source.JPG by sweeping both knobs and reading the output.
# Note ink% is a poor guide here: CLAHE renormalises to full range before the
# curve, so total ink tracks the silhouette's share of the frame, not gamma.
# What responds is the count of near-solid rows -- the suit. Widening the crop
# from this took it from 0 heavy rows to 5, which is a fifth of the portrait
# turned into an unreadable block.
GAMMA = 1.6
CLAHE_CLIP = 3.0
CROP = (0.27, 0.09, 0.79, 0.43)   # x0,y0,x1,y1 -- head, shoulders, tie knot
ROW_DELAY = 0.09          # stagger between rows
ROW_DUR = 0.55            # wipe duration for one row


def cutout(path: Path) -> np.ndarray:
    """Force everything outside the subject to white.

    White maps to the blank end of the ramp. Skip this and the background fills
    with '@' and drowns the portrait.
    """
    from rembg import remove

    img = Image.open(path).convert("RGBA")
    # 90 columns needs nowhere near a 4672x7008 source, and u2net downsamples to
    # 320x320 internally anyway -- the full-resolution alpha composite is pure
    # cost. 2000px long edge still leaves ~20 source pixels per character.
    if max(img.size) > 2000:
        img.thumbnail((2000, 2000), Image.LANCZOS)
    cut = remove(img)
    flat = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    flat.alpha_composite(cut)
    return cv2.cvtColor(np.array(flat.convert("RGB")), cv2.COLOR_RGB2BGR)


def prepare(bgr: np.ndarray, crop, gamma: float, clip: float) -> np.ndarray:
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = crop
    bgr = bgr[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Smooth skin, keep edges.
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    # Local contrast per tile. Global autocontrast leaves a flatly-lit face as
    # one flat tone, which is exactly this photo's problem.
    gray = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(gray)
    # The darkening curve. This is what makes features survive.
    return (np.power(gray / 255.0, gamma) * 255).astype(np.uint8)


def to_rows(gray: np.ndarray, cols: int) -> list[str]:
    h, w = gray.shape
    rows = max(1, int(cols * (h / w) * 0.48))
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)
    idx = ((255 - small) / 255.0 * (len(RAMP) - 1)).round().astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]


def to_svg(rows: list[str]) -> str:
    """One clipPath per row, its rect wiped 0 -> full width, with a block riding
    the edge as a cursor. fill="freeze" everywhere so it prints once and stops.

    Motion has to be SMIL: GitHub strips scripts, but it does run animate/set.
    """
    grid_w = COLS * CHAR_W
    grid_h = len(rows) * LINE_H
    height = DISPLAY_W * grid_h / grid_w

    style = (
        font_face("ramp")
        + theme_vars()
        + f"text{{font-family:'JBM',monospace;font-size:{FONT_SIZE}px;"
        "fill:var(--fg);white-space:pre;dominant-baseline:hanging}"
        + "rect.cur{fill:var(--fg)}"
    )

    defs, body = [], []
    for i, row in enumerate(rows):
        y = i * LINE_H
        w = len(row.rstrip()) * CHAR_W
        if w <= 0:
            continue
        begin = f"{i * ROW_DELAY:.2f}s"
        defs.append(
            f'<clipPath id="c{i}"><rect x="0" y="{y:.2f}" width="0" height="{LINE_H:.2f}">'
            f'<animate attributeName="width" from="0" to="{w:.2f}" begin="{begin}" '
            f'dur="{ROW_DUR}s" fill="freeze"/></rect></clipPath>'
        )
        safe = row.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body.append(f'<text x="0" y="{y:.2f}" clip-path="url(#c{i})">{safe}</text>')
        # Cursor: rides the wipe edge, then disappears.
        body.append(
            f'<rect class="cur" x="0" y="{y:.2f}" width="{CHAR_W:.2f}" '
            f'height="{LINE_H:.2f}" opacity="0">'
            f'<set attributeName="opacity" to="0.55" begin="{begin}" fill="freeze"/>'
            f'<animate attributeName="x" from="0" to="{w:.2f}" begin="{begin}" '
            f'dur="{ROW_DUR}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0" '
            f'begin="{i * ROW_DELAY + ROW_DUR:.2f}s" fill="freeze"/></rect>'
        )

    inner = f"<defs>{''.join(defs)}</defs>{''.join(body)}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{DISPLAY_W}" '
        f'height="{height:.0f}" viewBox="0 0 {grid_w:.2f} {grid_h:.2f}" '
        f'role="img" aria-label="ASCII portrait of Rasty Cannu Espartero, '
        f'drawn one row at a time.">'
        f"<style>{style}</style>{inner}</svg>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", type=Path, default=ROOT / "photo" / "source.jpg")
    ap.add_argument("--gamma", type=float, default=GAMMA)
    ap.add_argument("--clip", type=float, default=CLAHE_CLIP)
    ap.add_argument("--cols", type=int, default=COLS)
    ap.add_argument("--crop", type=str, default=",".join(str(c) for c in CROP))
    ap.add_argument("--preview", action="store_true", help="print text, skip SVG")
    a = ap.parse_args()

    if not a.photo.exists():
        raise SystemExit(
            f"no photo at {a.photo}\n"
            "Save your headshot there (jpg or png), then re-run."
        )

    crop = tuple(float(v) for v in a.crop.split(","))
    rows = to_rows(prepare(cutout(a.photo), crop, a.gamma, a.clip), a.cols)

    if a.preview:
        print("\n".join(rows))
        ink = sum(c != " " for r in rows for c in r) / sum(len(r) for r in rows)
        print(f"\n{len(rows)} rows x {a.cols} cols, gamma {a.gamma}, ink {ink:.0%}")
        return

    print("portrait")
    write(ROOT / "portrait.svg", to_svg(rows))
    total = (len(rows) - 1) * ROW_DELAY + ROW_DUR
    print(f"  {len(rows)} rows, finishes typing in {total:.1f}s")


if __name__ == "__main__":
    main()

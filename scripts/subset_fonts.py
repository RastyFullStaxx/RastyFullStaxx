"""Subset JetBrains Mono into per-role woff2 files.

Every SVG carries its own base64 copy of the font it needs. An external font URL
cannot work here: these SVGs load through an <img> tag, and browsers refuse
subresource fetches for image documents. A @font-face with a data: URI does work.

Inlining a full TTF into each file would be ~4.5 MB; these subsets total ~12 KB.

Run once:  python scripts/subset_fonts.py /path/to/jetbrains/ttf
"""
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts"

# The 13 brightness levels the portrait draws with. The leading space is what
# clears the cut-out background to nothing.
RAMP = " .`:-=+*cs#%@"

# Only the letters that actually appear in the section headings.
HEADINGS = "".join(sorted(set("statsstackwork")))

# Basic latin, plus the few punctuation marks the graphics actually use.
# The middot separates stack items; without it the glyph falls back to tofu.
BASIC_LATIN = "".join(chr(c) for c in range(0x20, 0x7F)) + "·—…"

# The portrait grid bakes in an advance of exactly 0.600 em (CHAR_W = 7.74 at
# font-size 12.9). JetBrains Mono is 600/1000 units, which is why it was chosen:
# embedding it changes no geometry. Verified, not assumed.
EXPECTED_ADVANCE = 0.600


def verify_advance(ttf: Path) -> None:
    font = TTFont(ttf)
    upem = font["head"].unitsPerEm
    # 'space' is present in every subset and is a safe probe for a mono advance.
    advance = font["hmtx"]["space"][0] / upem
    if abs(advance - EXPECTED_ADVANCE) > 0.0005:
        raise SystemExit(
            f"{ttf.name}: advance is {advance:.4f} em, expected {EXPECTED_ADVANCE}.\n"
            "The portrait grid assumes 0.600. Using this font would shift every "
            "column. Pick a font with a 600/1000 advance or recompute CHAR_W."
        )
    print(f"  advance {advance:.3f} em  ok")


def subset(ttf: Path, text: str, name: str) -> None:
    out = OUT / f"{name}.woff2"
    subprocess.run(
        [
            sys.executable, "-m", "fontTools.subset", str(ttf),
            f"--text={text}",
            "--flavor=woff2",
            "--layout-features=",
            "--no-hinting",
            f"--output-file={out}",
        ],
        check=True,
    )
    print(f"  {out.name:<22} {out.stat().st_size / 1024:5.1f} KB  ({len(set(text))} chars)")


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "assets" / "fonts"
    regular, bold = src / "JetBrainsMono-Regular.ttf", src / "JetBrainsMono-Bold.ttf"
    for f in (regular, bold):
        if not f.exists():
            raise SystemExit(f"missing {f}")

    OUT.mkdir(parents=True, exist_ok=True)
    print("verifying advance width")
    verify_advance(regular)

    print("subsetting")
    subset(regular, RAMP, "ramp")
    subset(bold, HEADINGS, "head")
    subset(regular, BASIC_LATIN, "text-regular")
    subset(bold, BASIC_LATIN, "text-bold")

    total = sum(f.stat().st_size for f in OUT.glob("*.woff2")) / 1024
    print(f"\ntotal {total:.1f} KB")


if __name__ == "__main__":
    main()

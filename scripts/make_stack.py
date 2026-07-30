"""The tech stack, drawn in our own type.

Replaces six rows of skillicons.dev images. No logos: on a monochrome page a
grid of brand-coloured icons is the one thing that cannot be made to match, and
it was the largest third-party dependency on the old README.

Run once:  python scripts/make_stack.py
"""
from xml.sax.saxutils import escape

from svgkit import ROOT, font_face, svg, theme_vars, write

W = 760
SIZE = 13
CHAR = SIZE * 0.600      # 0.600 em advance -- the same constant everywhere
LABEL_X = 0
ITEM_X = 132
LINE_H = 20
GROUP_GAP = 12
TOP = 18
SEP = "  ·  "

# Mirrors the six categories and every entry from the previous README's icon
# rows, in the same order. Nothing dropped in the move away from skillicons.
STACK = [
    ("languages", ["Java", "C#", "C++", "C", "Python", "PHP", "JavaScript",
                   "TypeScript", "Bash", "MySQL"]),
    ("backend & api", ["Node.js", "Express", "Spring", ".NET", "FastAPI",
                       "GraphQL", "Redis", "PostgreSQL", "MongoDB", "SQLite"]),
    ("frontend", ["React", "Next.js", "Vue", "Svelte", "Bootstrap", "Tailwind",
                  "HTML", "CSS"]),
    ("ml & data", ["TensorFlow", "PyTorch", "scikit-learn", "Anaconda",
                   "pandas", "NumPy"]),
    ("devops & cloud", ["Docker", "Kubernetes", "Terraform", "AWS", "GCP",
                        "Azure", "nginx", "Linux", "Bash"]),
    ("tools", ["Git", "GitHub", "GitLab", "VS Code", "IntelliJ IDEA", "Figma",
               "Postman"]),
]


def wrap(items: list[str], max_chars: int) -> list[str]:
    """Greedy wrap on the separator. Mono means width is just a character count."""
    lines: list[str] = []
    cur = ""
    for item in items:
        candidate = item if not cur else cur + SEP + item
        if len(candidate) > max_chars and cur:
            lines.append(cur)
            cur = item
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    return lines


def build() -> str:
    max_chars = int((W - ITEM_X) / CHAR)
    style = (
        font_face("text-regular", weight=400)
        + font_face("text-bold", weight=700)
        + theme_vars()
        + f"text{{font-family:'JBM',monospace;font-size:{SIZE}px}}"
        + ".l{font-weight:700;fill:var(--dim)}"
        + ".i{font-weight:400;fill:var(--fg)}"
    )

    parts, y, spoken = [], TOP, []
    for label, items in STACK:
        lines = wrap(items, max_chars)
        # escape(): "ml & data" is a raw ampersand, which is invalid XML and
        # fails the whole document, not just the one node.
        parts.append(f'<text class="l" x="{LABEL_X}" y="{y}">{escape(label)}</text>')
        for i, line in enumerate(lines):
            parts.append(
                f'<text class="i" x="{ITEM_X}" y="{y + i * LINE_H}">{escape(line)}</text>'
            )
        y += len(lines) * LINE_H + GROUP_GAP
        spoken.append(f"{label}: {', '.join(items)}")

    height = y - GROUP_GAP + 8
    return svg(W, height, style, "".join(parts), "Tech stack. " + ". ".join(spoken))


def main() -> None:
    print("stack")
    write(ROOT / "stack.svg", build())


if __name__ == "__main__":
    main()

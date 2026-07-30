"""The tech stack, drawn in our own type.

Replaces six rows of skillicons.dev images. No logos: on a monochrome page a
grid of brand-coloured icons is the one thing that cannot be made to match, and
it was the largest third-party dependency on the old README.

Run once:  python scripts/make_stack.py
"""
from xml.sax.saxutils import escape

from svgkit import ROOT, font_face, svg, theme_vars, write

from svgkit import W          # narrow canvas: renders 1:1, no downscaled type

SIZE = 13
CHAR = SIZE * 0.600      # 0.600 em advance -- the same constant everywhere
LABEL_X = 0
ITEM_X = 148          # widest label is "ml & data science"
LINE_H = 20
GROUP_GAP = 12
TOP = 18
SEP = "  ·  "

# Built from what the public repos actually contain -- manifests read from
# fnb-lis, CureRays-CRMS, IntelliForm, AgilaEye, digiphoto-booth-system and
# PharmaSynth, plus the language breakdown GitHub reports. Anything listed here
# should be defensible in an interview.
STACK = [
    ("languages", ["C#", "TypeScript", "JavaScript", "Python", "PHP", "Java",
                   "C", "C++", "SQL", "Bash", "PowerShell", "R"]),
    ("backend & api", ["Node.js", ".NET", "FastAPI", "Hono", "Express",
                       "Laravel", "Spring", "Uvicorn", "Zod", "Pydantic",
                       "REST", "GraphQL"]),
    ("data", ["Prisma", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis",
              "ExcelJS", "pandas"]),
    ("frontend", ["Next.js", "React", "Svelte", "Vue", "Vite", "Tailwind",
                  "Bootstrap", "Blade", "HTML", "CSS"]),
    ("ml & data science", ["PyTorch", "Transformers", "TensorFlow",
                           "scikit-learn", "NumPy", "SciPy", "NLTK",
                           "Jupyter", "pdfplumber", "PyMuPDF", "Pillow"]),
    ("apps & desktop", ["Electron", "Tauri", "Unity", "WPF", "ffmpeg"]),
    ("visualisation", ["ECharts", "Recharts", "D3", "Three.js", "pdfmake",
                       "docxtemplater"]),
    ("devops & cloud", ["Docker", "GitHub Actions", "Kubernetes", "Terraform",
                        "AWS", "GCP", "Azure", "nginx", "Linux"]),
    ("testing", ["Playwright", "Vitest", "Testing Library", "pytest"]),
    ("tools", ["Git", "GitHub", "GitLab", "VS Code", "Visual Studio",
               "IntelliJ IDEA", "Figma", "Postman"]),
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

"""Draw stats.svg, streak.svg, langs.svg and year.svg from the GitHub GraphQL API.

Standard library only -- urllib for the API. This runs nightly in CI and there is
nothing here that can break when a dependency ships a new major.

    python scripts/generate_stats.py          # needs GITHUB_TOKEN, GH_LOGIN
    python scripts/generate_stats.py --check  # self-check, no network
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from svgkit import W, ROOT, escape, font_face, svg, theme_vars, write

API = "https://api.github.com/graphql"
RAMP = " .`:-=+*cs#%@"          # the portrait's own ramp, reused for the year grid
TOP_LANGS = 8                   # a wide stack; 6 cut off real languages

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!, $cursor:String) {
  user(login:$login) {
    createdAt
    followers { totalCount }
    repositoriesContributedTo(
      contributionTypes:[COMMIT,PULL_REQUEST,ISSUE,REPOSITORY,PULL_REQUEST_REVIEW]
    ) { totalCount }
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first:100, after:$cursor, privacy:PUBLIC, ownerAffiliations:OWNER,
                 isFork:false, orderBy:{field:PUSHED_AT, direction:DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        forkCount
        languages(first:15, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------

def window(now: datetime) -> tuple[str, str]:
    """Pin the contribution window to whole UTC days.

    Left alone, contributionsCollection measures "the past year" from the moment
    of the request. Two runs minutes apart bucket days into different weeks and
    shift the sparkline by a fraction of a pixel -- enough that the file differs
    every night and the workflow commits noise forever.
    """
    today = now.astimezone(timezone.utc).date()
    start = today - timedelta(days=364)
    return f"{start}T00:00:00Z", f"{today}T23:59:59Z"


def _post(query: str, variables: dict, token: str, login: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-profile-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(login: str, token: str) -> dict:
    """Page through every public repo, not just the first 100."""
    frm, to = window(datetime.now(timezone.utc))
    base = {"login": login, "from": frm, "to": to}

    user = _post(QUERY, {**base, "cursor": None}, token, login)
    nodes = user["repositories"]["nodes"]
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        more = _post(QUERY, {**base, "cursor": page["endCursor"]}, token, login)
        nodes.extend(more["repositories"]["nodes"])
        page = more["repositories"]["pageInfo"]
    user["repositories"]["nodes"] = nodes
    return user


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------

def days(user: dict) -> list[tuple[str, int]]:
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [
        (d["date"], d["contributionCount"])
        for w in weeks
        for d in w["contributionDays"]
    ]


def streaks(day_list: list[tuple[str, int]]) -> dict:
    """Current and longest run of consecutive days with at least one contribution.

    Today counts as neutral, not as a break: a run is still live until the day
    ends, and reporting it broken before midnight UTC is just wrong.
    """
    best = cur = 0
    best_range = cur_range = ("", "")
    for date, count in day_list:
        if count > 0:
            cur = cur + 1 if cur else 1
            cur_range = (cur_range[0] if cur > 1 else date, date)
            if cur > best:
                best, best_range = cur, cur_range
        else:
            is_today = date == day_list[-1][0]
            if not is_today:
                cur, cur_range = 0, ("", "")
    return {
        "current": cur,
        "current_range": cur_range,
        "longest": best,
        "longest_range": best_range,
    }


def weekly(day_list: list[tuple[str, int]]) -> list[int]:
    return [sum(c for _, c in day_list[i:i + 7]) for i in range(0, len(day_list), 7)]


def languages(user: dict) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Top languages by bytes, and by number of repositories.

    Two rankings because they disagree, and the disagreement is the interesting
    part: one big generated file can dominate bytes while a language you actually
    reach for daily shows up in far more repos.
    """
    by_bytes: dict[str, int] = {}
    by_repo: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        seen = set()
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            by_bytes[name] = by_bytes.get(name, 0) + edge["size"]
            seen.add(name)
        for name in seen:
            by_repo[name] = by_repo.get(name, 0) + 1
    top = lambda d: sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_LANGS]
    return top(by_bytes), top(by_repo)


# --------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------

def base_style(extra: str = "") -> str:
    return (
        font_face("text-regular", weight=400)
        + font_face("text-bold", weight=700)
        + theme_vars()
        + "text{font-family:'JBM',monospace;fill:var(--fg)}"
        + ".d{fill:var(--dim)}.b{font-weight:700}"
        + "rect.bar{fill:var(--fg)}rect.tr{fill:var(--faint)}"
        + extra
    )


def fmt(n: int) -> str:
    return f"{n / 1000:.2f}k" if n >= 1000 else str(n)


MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]


def nice_date(iso: str) -> str:
    """2026-07-25 -> jul 25"""
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m) - 1]} {int(d)}"


def draw_stats(user: dict, day_list: list[tuple[str, int]]) -> str:
    c = user["contributionsCollection"]
    total = c["contributionCalendar"]["totalContributions"]
    wk = weekly(day_list)
    active = sum(1 for _, n in day_list if n > 0)
    H = 128

    p = [
        f'<text class="b" x="0" y="44" font-size="38">{total}</text>',
        '<text class="d" x="0" y="62" font-size="11">contributions in the last year</text>',
        f'<text x="{W}" y="22" font-size="15" text-anchor="end">{active}</text>',
        f'<text class="d" x="{W}" y="35" font-size="10" text-anchor="end">active days</text>',
        f'<text x="{W}" y="56" font-size="15" text-anchor="end">{max(wk)}</text>',
        f'<text class="d" x="{W}" y="69" font-size="10" text-anchor="end">best week</text>',
    ]

    # Weekly aggregate, so a line is defensible here -- continuity is real.
    # Daily counts are sparse and discrete and get characters instead; a line
    # through 0, 0, 11, 0 would claim values that never existed. See draw_year.
    peak = max(wk) or 1
    gy, gh = H - 10, 38
    step = W / (len(wk) - 1)
    pts = " ".join(f"{i * step:.1f},{gy - v / peak * gh:.1f}" for i, v in enumerate(wk))
    p.append(f'<polyline points="0,{gy} {pts} {W},{gy}" fill="var(--fg)" opacity="0.09"/>')
    p.append(f'<polyline points="{pts}" fill="none" stroke="var(--fg)" stroke-width="1.3" '
             'stroke-linejoin="round" stroke-linecap="round"/>')
    # Mark where the line ends, so "now" is unambiguous.
    p.append(f'<circle cx="{W}" cy="{gy - wk[-1] / peak * gh:.1f}" r="3" fill="var(--fg)"/>')

    return svg(W, H, base_style(), "".join(p),
               f"{total} contributions in the last year. {active} active days. "
               f"Best week {max(wk)}. Weekly totals shown as a sparkline.")


def draw_streak(s: dict) -> str:
    H = 84
    MID = 190                      # divider; the two halves read as one panel
    span = lambda r: f"{nice_date(r[0])} – {nice_date(r[1])}" if r[0] else "—"

    p = []
    for x, n, label, rng in (
        (0, s["current"], "current streak", s["current_range"]),
        (MID + 26, s["longest"], "longest streak", s["longest_range"]),
    ):
        p += [
            f'<text class="b" x="{x}" y="38" font-size="32">{n}</text>',
            f'<text class="d" x="{x}" y="58" font-size="11">{label}</text>',
            f'<text class="d" x="{x}" y="74" font-size="10">{span(rng)}</text>',
        ]
    p.append(f'<line x1="{MID}" y1="8" x2="{MID}" y2="{H - 6}" '
             'stroke="var(--faint)" stroke-width="1"/>')

    return svg(W, H, base_style(), "".join(p),
               f"Current streak {s['current']} days, {span(s['current_range'])}. "
               f"Longest streak {s['longest']} days, {span(s['longest_range'])}.")


def draw_langs(by_bytes: list, by_repo: list) -> str:
    ROW = 20
    COL = 188                      # column width
    NAME_W = 74                    # name gutter, then the bar starts
    BAR_MAX = 74
    SIZE = 11
    H = 26 + max(len(by_bytes), len(by_repo)) * ROW

    total = sum(v for _, v in by_bytes) or 1
    peak = max((v for _, v in by_repo), default=1) or 1
    p = []

    def column(x0: int, items: list, head: str, denom: int, fmt_val) -> None:
        p.append(f'<text class="d" x="{x0}" y="10" font-size="10">{head}</text>')
        for i, (name, v) in enumerate(items):
            y = 30 + i * ROW
            p.append(f'<text x="{x0}" y="{y}" font-size="{SIZE}">{escape(name.lower())}</text>')
            p.append(f'<rect class="bar" x="{x0 + NAME_W}" y="{y - 7}" rx="1.5" '
                     f'width="{BAR_MAX * v / denom:.1f}" height="6"/>')
            p.append(f'<text class="d" x="{x0 + COL}" y="{y}" font-size="10" '
                     f'text-anchor="end">{fmt_val(v)}</text>')

    column(0, by_bytes, "by bytes", total, lambda v: f"{v / total * 100:.0f}%")
    column(212, by_repo, "by repos", peak, str)

    label = "Top languages by bytes: " + ", ".join(
        f"{k} {v / total * 100:.0f} percent" for k, v in by_bytes
    ) + ". By repository count: " + ", ".join(f"{k} {v}" for k, v in by_repo)
    return svg(W, H, base_style(), "".join(p), label)


def draw_year(day_list: list[tuple[str, int]]) -> str:
    """The year at one character per day, using the portrait's own ramp.

    Characters, not rectangles: it is the one graphic that ties the data half of
    the page back to the portrait.
    """
    SIZE = 9
    CHAR = SIZE * 0.600
    ROW = 11
    GX = 26                        # grid left edge; weekday labels sit left of it
    GY = 52                        # first grid row baseline
    peak = max(c for _, c in day_list) or 1

    grid: dict[tuple[int, int], str] = {}
    for i, (_, count) in enumerate(day_list):
        week, dow = i // 7, i % 7
        # +1 so any activity at all clears the blank slot: a day with one
        # contribution must not look identical to a day with none.
        level = 0 if count == 0 else 1 + int(count / peak * (len(RAMP) - 2))
        grid[(week, dow)] = RAMP[min(level, len(RAMP) - 1)]

    weeks = max(w for w, _ in grid) + 1
    week_w = (W - GX) / weeks
    nbsp = lambda s: s.replace(" ", "&#160;")

    p = []
    active = sum(1 for _, n in day_list if n > 0)
    p.append('<text class="d" x="0" y="10" font-size="10">the year</text>')
    p.append(f'<text class="d" x="0" y="26" font-size="10">{active} of '
             f'{len(day_list)} days had a contribution</text>')

    # Density legend. Without it the ramp is just texture.
    legend = "".join(RAMP[i] for i in (1, 6, 10, 12))
    p.append(f'<text class="d" x="{W - 60}" y="26" font-size="9" '
             f'text-anchor="end">less</text>')
    p.append(f'<text x="{W - 56}" y="26" font-size="9" '
             f'letter-spacing="2">{escape(legend)}</text>')
    p.append(f'<text class="d" x="{W}" y="26" font-size="9" '
             f'text-anchor="end">more</text>')

    # Weekday labels. Mon/Wed/Fri only -- all seven is noise at this row height.
    for dow, name in ((1, "mon"), (3, "wed"), (5, "fri")):
        p.append(f'<text class="d" x="0" y="{GY + dow * ROW}" font-size="8">{name}</text>')

    for dow in range(7):
        line = "".join(grid.get((w, dow), " ") for w in range(weeks))
        p.append(f'<text class="g" x="{GX}" y="{GY + dow * ROW}">{nbsp(escape(line))}</text>')

    # Month labels, placed at the week each month first appears. Skip a label
    # that would collide with the previous one.
    last_x = -999
    for w in range(weeks):
        iso = next((d for i, (d, _) in enumerate(day_list)
                    if i // 7 == w and i % 7 == 0), None)
        if not iso:
            continue
        mon, day = int(iso[5:7]), int(iso[8:10])
        if day > 7:                      # only the week containing the 1st-7th
            continue
        x = GX + w * week_w
        if x - last_x < 26:
            continue
        last_x = x
        p.append(f'<text class="d" x="{x:.1f}" y="{GY + 7 * ROW + 2}" '
                 f'font-size="8">{MONTHS[mon - 1]}</text>')

    style = (
        font_face("text-regular", weight=400) + theme_vars()
        + f"text{{font-family:'JBM',monospace;fill:var(--fg)}}"
        + ".d{fill:var(--dim)}"
        + f".g{{font-size:{SIZE}px;letter-spacing:{week_w - CHAR:.3f}px;white-space:pre}}"
    )
    total = sum(c for _, c in day_list)
    return svg(W, GY + 7 * ROW + 10, style, "".join(p),
               f"Contribution grid for the last year. {total} contributions across "
               f"{active} active days, one character per day.")


# --------------------------------------------------------------------------
# self-check
# --------------------------------------------------------------------------

def check() -> None:
    """The smallest thing that fails if the determinism or streak logic breaks."""
    now = datetime(2026, 7, 31, 13, 45, 9, tzinfo=timezone.utc)
    frm, to = window(now)
    assert (frm, to) == ("2025-08-01T00:00:00Z", "2026-07-31T23:59:59Z"), (frm, to)

    # Same UTC day, very different clock times -> byte-identical window.
    late = datetime(2026, 7, 31, 23, 59, 58, tzinfo=timezone.utc)
    assert window(late) == (frm, to), "window drifts within a single UTC day"

    # 365 whole days inclusive.
    d0 = datetime.fromisoformat(frm.replace("Z", "+00:00")).date()
    d1 = datetime.fromisoformat(to.replace("Z", "+00:00")).date()
    assert (d1 - d0).days + 1 == 365

    d = lambda n: f"2026-01-{n:02d}"
    broken = [(d(1), 3), (d(2), 1), (d(3), 0), (d(4), 2), (d(5), 5), (d(6), 4)]
    s = streaks(broken)
    assert s["longest"] == 3 and s["longest_range"] == (d(4), d(6)), s
    assert s["current"] == 3, s

    # A zero on the final day must not break a live run.
    s = streaks([(d(1), 2), (d(2), 4), (d(3), 0)])
    assert s["current"] == 2, s

    # A zero anywhere earlier must.
    s = streaks([(d(1), 2), (d(2), 0), (d(3), 4)])
    assert s["current"] == 1, s

    assert weekly([("", 1)] * 14) == [7, 7]
    assert fmt(3340) == "3.34k" and fmt(52) == "52"
    print("self-check ok")


def main() -> None:
    if "--check" in sys.argv:
        return check()

    login = os.environ.get("GH_LOGIN")
    token = os.environ.get("GITHUB_TOKEN")
    if not login or not token:
        raise SystemExit("set GH_LOGIN and GITHUB_TOKEN")

    user = fetch(login, token)
    day_list = days(user)
    by_bytes, by_repo = languages(user)

    print("stats")
    write(ROOT / "stats.svg", draw_stats(user, day_list))
    write(ROOT / "streak.svg", draw_streak(streaks(day_list)))
    write(ROOT / "langs.svg", draw_langs(by_bytes, by_repo))
    write(ROOT / "year.svg", draw_year(day_list))


if __name__ == "__main__":
    main()

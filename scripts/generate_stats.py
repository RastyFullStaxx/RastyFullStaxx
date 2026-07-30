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

from svgkit import ROOT, font_face, svg, theme_vars, write

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


def draw_stats(user: dict, day_list: list[tuple[str, int]]) -> str:
    c = user["contributionsCollection"]
    total = c["contributionCalendar"]["totalContributions"]
    repos = user["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    forks = sum(r["forkCount"] for r in repos)
    since = user["createdAt"][:4]
    W, H = 370, 232
    p = [
        f'<text class="d" x="0" y="16" font-size="11">contributions, last 365 days</text>',
        f'<text class="b" x="0" y="58" font-size="38">{fmt(total)}</text>',
    ]

    rows = [
        ("commits", fmt(c["totalCommitContributions"])),
        ("pull requests", c["totalPullRequestContributions"]),
        ("reviews", c["totalPullRequestReviewContributions"]),
        ("issues", c["totalIssueContributions"]),
        ("public repos", user["repositories"]["totalCount"]),
        ("contributed to", user["repositoriesContributedTo"]["totalCount"]),
        ("stars earned", stars),
        ("forks", forks),
        ("followers", user["followers"]["totalCount"]),
        ("on github since", since),
    ]
    for i, (label, value) in enumerate(rows):
        y = 84 + i * 15
        p.append(f'<text class="d" x="0" y="{y}" font-size="12">{label}</text>')
        p.append(f'<text x="{W}" y="{y}" font-size="12" text-anchor="end">{value}</text>')

    # Weekly aggregate, so a line is defensible here -- continuity is real.
    # Daily counts get columns instead; see draw_year.
    wk = weekly(day_list)
    peak = max(wk) or 1
    gy, gh = H - 4, 34
    step = W / (len(wk) - 1)
    pts = " ".join(f"{i * step:.1f},{gy - v / peak * gh:.1f}" for i, v in enumerate(wk))
    p.append(f'<polyline points="{pts}" fill="none" stroke="var(--fg)" stroke-width="1.2" '
             'stroke-linejoin="round"/>')
    p.append(f'<polyline points="0,{gy} {pts} {W},{gy}" fill="var(--fg)" opacity="0.10"/>')

    label = (f"{total} contributions in the last 365 days. "
             + ". ".join(f"{k}: {v}" for k, v in rows))
    return svg(W, H, base_style(), "".join(p), label)


def draw_streak(s: dict) -> str:
    W, H = 370, 232
    span = lambda r: f"{r[0]} to {r[1]}" if r[0] else "--"
    p = [
        '<text class="d" x="0" y="16" font-size="11">streak</text>',
        f'<text class="b" x="0" y="58" font-size="38">{s["current"]}</text>',
        f'<text class="d" x="0" y="78" font-size="12">current, days</text>',
        f'<text class="d" x="0" y="96" font-size="10">{span(s["current_range"])}</text>',
        f'<line x1="0" y1="124" x2="{W}" y2="124" stroke="var(--faint)" stroke-width="1"/>',
        f'<text class="b" x="0" y="168" font-size="38">{s["longest"]}</text>',
        f'<text class="d" x="0" y="188" font-size="12">longest, days</text>',
        f'<text class="d" x="0" y="206" font-size="10">{span(s["longest_range"])}</text>',
    ]
    label = (f"Current streak {s['current']} days, {span(s['current_range'])}. "
             f"Longest streak {s['longest']} days, {span(s['longest_range'])}.")
    return svg(W, H, base_style(), "".join(p), label)


def draw_langs(by_bytes: list, by_repo: list) -> str:
    W, H = 760, 38 + TOP_LANGS * 24
    col = 360
    p = []
    total = sum(v for _, v in by_bytes) or 1

    p.append('<text class="d" x="0" y="14" font-size="11">by bytes</text>')
    for i, (name, size) in enumerate(by_bytes):
        y, pct = 38 + i * 24, size / total * 100
        p.append(f'<text x="0" y="{y}" font-size="12">{name}</text>')
        p.append(f'<text class="d" x="{col}" y="{y}" font-size="11" '
                 f'text-anchor="end">{pct:.1f}%</text>')
        p.append(f'<rect class="tr" x="0" y="{y + 5}" width="{col}" height="3"/>')
        p.append(f'<rect class="bar" x="0" y="{y + 5}" width="{col * size / total:.1f}" height="3"/>')

    x0 = 400
    peak = max(v for _, v in by_repo) or 1
    p.append(f'<text class="d" x="{x0}" y="14" font-size="11">by repository</text>')
    for i, (name, n) in enumerate(by_repo):
        y = 38 + i * 24
        p.append(f'<text x="{x0}" y="{y}" font-size="12">{name}</text>')
        p.append(f'<text class="d" x="{W}" y="{y}" font-size="11" text-anchor="end">{n}</text>')
        p.append(f'<rect class="tr" x="{x0}" y="{y + 5}" width="{W - x0}" height="3"/>')
        p.append(f'<rect class="bar" x="{x0}" y="{y + 5}" '
                 f'width="{(W - x0) * n / peak:.1f}" height="3"/>')

    label = "Top languages by bytes: " + ", ".join(
        f"{k} {v / total * 100:.1f} percent" for k, v in by_bytes
    ) + ". By repository: " + ", ".join(f"{k} {v}" for k, v in by_repo)
    return svg(W, H, base_style(), "".join(p), label)


def draw_year(day_list: list[tuple[str, int]]) -> str:
    """The year at one character per day, using the portrait's own ramp.

    Characters, not rectangles: it is the one graphic that ties the data half of
    the page back to the portrait.
    """
    W = 760
    SIZE = 11
    CHAR = SIZE * 0.600
    ROW = 13
    peak = max(c for _, c in day_list) or 1

    grid: dict[tuple[int, int], str] = {}
    for i, (_, count) in enumerate(day_list):
        week, dow = i // 7, i % 7
        if count == 0:
            level = 0
        else:
            # +1 so any activity at all clears the blank slot.
            level = 1 + int(count / peak * (len(RAMP) - 2))
        grid[(week, dow)] = RAMP[min(level, len(RAMP) - 1)]

    weeks = max(w for w, _ in grid) + 1
    rows = []
    for dow in range(7):
        line = "".join(grid.get((w, dow), " ") for w in range(weeks))
        rows.append(f'<text x="0" y="{16 + dow * ROW}">{line.replace(" ", "&#160;")}</text>')

    style = (
        font_face("ramp") + theme_vars()
        + f"text{{font-family:'JBM',monospace;font-size:{SIZE}px;fill:var(--fg);"
        f"letter-spacing:{W / weeks - CHAR:.3f}px;white-space:pre}}"
    )
    total = sum(c for _, c in day_list)
    return svg(W, 16 + 7 * ROW, style, "".join(rows),
               f"Contribution grid for the last year, {total} contributions, "
               f"one character per day.")


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

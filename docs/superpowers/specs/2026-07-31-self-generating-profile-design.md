# Self-generating GitHub profile — design

**Date:** 2026-07-31
**Repo:** `RastyFullStaxx/RastyFullStaxx`
**Goal:** Replace a README built entirely from third-party image services with one
generated inside this repository. Zero third-party requests at render time.

## Why

The current README sources every graphic from someone else's server:
`github-profile-summary-cards.vercel.app`, `skillicons.dev`, `cdn.jsdelivr.net`,
`capsule-render.vercel.app`. Two failure modes:

1. **They break.** Rate limits and outages hit the one page where a broken image
   costs the most.
2. **They can't be designed.** Five vendors means five visual languages on one page.

Everything below is drawn by this repo. The rendered page makes zero third-party
requests.

## What GitHub's sanitiser allows

Established by posting markdown to `POST /markdown` and reading back what survived.

```
STRIPPED
  <style> blocks      style="" attributes     class=""
  inline <svg>        <font>  <small>  <big>
KEPT
  <sub> <sup> <kbd> <samp> <blockquote> <details> <hr> <picture>
  align=""    width="" on <img> and <td>
```

Consequences:

- README text cannot change typeface. Anything in our own type must be an image.
- Scripts are stripped, so animation must be SMIL (`animate`, `set`) inside the SVG.
- `<style>` is stripped from *markdown*, but an SVG is a separate document that never
  passes through the sanitiser. `<style>` inside an SVG file works, including media
  queries. This is what makes single-file light/dark theming possible.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Scope | Portrait + stats (both halves) | — |
| Crop | Head + shoulders, ending just past the tie knot | White collar and tie are the only tonal structure below the jaw; stopping there keeps that contrast and avoids an unbroken suit slab |
| Palette | Monochrome, single fill | `#e6edf3` dark / `#1f2328` light |
| Theming | `prefers-color-scheme` inside each SVG's own `<style>` | One file per graphic, no `<picture>` duplication |
| Tech stack | Drawn as `stack.svg` in our own type | Only option preserving one visual language |
| Banner | Deleted | Two headers stacked; the portrait is the stronger opening |
| Copy | Three icon lists merged into one "work" section | The originals restated the same 3–4 ideas under different headings |

**Known ceiling on theming:** `prefers-color-scheme` follows the visitor's OS, not
their GitHub setting. A visitor on light OS with GitHub set to dark gets the light
variant. The `<picture>` approach has the identical limitation — there is no better
option available.

## Artifact ownership

Two classes. Keeping them separate prevents the most expensive failure mode.

**Build-once, committed by hand:**
`portrait.svg`, `stack.svg`, `h-*.svg`, `assets/fonts/*`

**Action-owned, never generated locally:**
`stats.svg`, `streak.svg`, `langs.svg`, `year.svg`

> Regenerating the action-owned files locally guarantees merge conflicts. A personal
> token and the runner's token bucket days near a week boundary differently, so the
> output is never byte-identical even when the underlying numbers agree.

## Layout

```
README.md
portrait.svg  stack.svg
h-stats.svg   h-stack.svg   h-work.svg
stats.svg  streak.svg  langs.svg  year.svg      <- action-owned
assets/fonts/  ramp.woff2 head.woff2 text-regular.woff2 text-bold.woff2  OFL.txt
photo/source.jpg
scripts/
  subset_fonts.py   make_portrait.py   make_stack.py
  make_headings.py  generate_stats.py
.github/workflows/refresh-stats.yml
```

## Constants that must not drift

| Constant | Value | Why |
|---|---|---|
| Columns | 90 | Below ~88 the face muddies; much above and the block dominates the page |
| Display width | 460px | — |
| Rows | `cols * (h/w) * 0.48` | Mono glyphs are ~2x tall as wide |
| Advance | `CHAR_W = 7.74` at `font-size: 12.9` | Exactly 0.600 em |
| Ramp | `' .` + "`" + `:-=+*cs#%@'` | 13 levels; the leading space clears background to nothing |
| Row stagger | `begin="{i * 0.09}s"` | ~56 rows finishes in ~5.1 s |

## Fonts

JetBrains Mono, SIL OFL 1.1, 600/1000 units — exactly the 0.600 the grid assumes, so
embedding changes no geometry.

An external font URL **cannot** work: these SVGs load through `<img>`, and browsers
refuse subresource fetches for image documents. A `@font-face` with a base64 data URI
does work. Every SVG carries its own subset.

| Subset | Covers | Target size |
|---|---|---|
| `ramp` | the 13 ramp characters | ~1.3 KB |
| `head` | only letters used in headings | ~1.4 KB |
| `text-regular` / `text-bold` | basic latin | ~4.5 KB each |

Roughly 57 KB across the page. Inlining full TTFs instead would be ~4.5 MB.

The font file lands in a public repo, so it must be OFL or similar. `OFL.txt` ships
beside it.

## Portrait pipeline

| Stage | Purpose |
|---|---|
| `rembg` cut-out | Forces everything outside the subject to white, which maps to the blank end of the ramp. Skipped, the background fills with `@` and drowns the portrait |
| Bilateral filter | Smooths skin while keeping edges |
| CLAHE, clip ~3.0 | Local contrast per tile; global autocontrast leaves a flatly-lit face as one tone |
| Darkening curve `(v/255)^G` | What makes brows, lips and hair edges survive |
| Map to ramp | — |

**Source photo is flat frontal light** — the failure case the pipeline fights hardest.
Start `G = 1.9` (guide default is 1.7) and tune 1.8–2.1 by eye. Face occupies ~25% of
frame height, so usable head resolution after crop is ~500 px. Fine detail (braces)
will not survive and should not.

**Animation:** each row sits in a `clipPath` whose rect animates `width` 0 to full,
with a small block riding the wipe edge as a cursor. `fill="freeze"` on every
animation so the portrait prints once and stops. No looping.

**One fill colour.** Per-character colouring is what makes most ASCII portraits look
like static.

## Stats

Source: GitHub GraphQL API. `generate_stats.py` uses **only the standard library**
(`urllib`) — no dependencies to break in CI.

Four graphics: hero total + weekly sparkline; current and longest streak with date
ranges; top languages by bytes and by repo; the year at one character per day using
the portrait's own ramp.

### Determinism traps

Both produce a nightly stream of meaningless commits if missed.

1. **Pin the window to whole UTC days.** `from` = today − 364 at `00:00:00Z`,
   `to` = today at `23:59:59Z`. Left alone, `contributionsCollection` measures from
   the moment of the request; two runs minutes apart bucket days into different weeks
   and shift the sparkline by a fraction of a pixel.
2. **Filter repositories to `privacy: PUBLIC`.** A personal token sees private repos;
   the workflow's token does not. Without this, language percentages disagree
   depending on who ran the script.

### Chart types

Columns, not lines, for daily contributions. Daily counts are sparse and discrete — a
line through `0, 0, 11, 0, 0, 10` claims values that never existed; a zero day should
be empty space. Lines and areas are reserved for the weekly sparkline, where
continuity is defensible.

### Workflow

`cron: "17 5 * * *"` plus `workflow_dispatch`. **Deliberately no `push` trigger** —
this job commits, and a push trigger would re-run it on its own commit.
`permissions: contents: write`. Built-in `GITHUB_TOKEN` returns the same numbers as a
PAT, so no personal token is needed. Commit only when `git status --porcelain` is
non-empty.

## Verification

- `assert`-based `demo()` in `generate_stats.py` covering the UTC date-window
  computation and column scaling. This is the check that fails if determinism breaks.
- Every README revision goes through `POST /markdown` before commit — same sanitiser
  as the site.
- Verify the portrait with a **tall viewport, not `fullPage`**. Full-page screenshots
  restart SMIL and produce blank animated SVGs. Wait ~5.1 s for a 56-row portrait.

## Build order

1. Fonts — everything downstream assumes the 0.600 advance
2. Portrait — longest tuning loop, gated on visual review
3. Headings + stack
4. Stats generator + workflow
5. README assembly + sanitiser check

## Out of scope

- **Pinned repositories and bio** cannot be set through the API. No GraphQL mutation
  exists and the REST call needs a `user` scope. Both are manual, in the UI.
- **Pushing.** All commits stay local. The repository owner pushes.

## Note on caching

A newly created profile README is cached. If a change does not appear on the profile,
editing it once through the web UI forces a refresh.

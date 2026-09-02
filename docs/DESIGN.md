# DESIGN.md: the tracker dashboard's default design system

The design system for `pipeline/tracker.html`, the one piece of UI this repo ships. This is a
**default**, not a mandate: the palette, canvas, and type below are one reasonable choice for a
dense, at-a-glance operational dashboard. Restyle it however you like; the rules that matter are the
structural/accessibility ones below the token section, not the specific colors.

## Register: instrument panel

A dense operational dashboard you'll glance at daily benefits from restraint: a near-black neutral
canvas, thin hairlines, tabular numerals, one accent doing the semantic work, zero decorative chrome.
Think of the register any well-built internal ops console or monitoring dashboard uses: information
density over ornament, hierarchy from spacing and weight rather than color.

## Tokens (role-named: never hardcode hex/px in markup)

- **Canvas** `--bg:#0C0C0D` (neutral near-black; never `#000`, never accent-tinted). Surfaces
  `--surface:#131414` / `--surface-2:#191A1A`. Hairlines `--line:#242525`.
- **Ink** `--ink:#E6E7E3` (softened, not pure white) · `--ink-dim` · `--ink-faint`.
- **Accent** `--accent:#37D98C` with `--accent-ink:#06140D` for text on accent fills. **One accent,
  one job:** live/in-progress status + current selection. Never decorative, never in a shadow/glow,
  kept under ~5% of surface. Swap the hue for anything you like; it's a one-token change.
- **Status** by dot **+ label**, never hue alone: live→accent, attention/needs-action→amber, negative
  →muted red (rare), neutral/muted→ink tones. ≤5 total colors.
- **Type** any clean sans with real tabular-figure support (Manrope, Inter, and most system UI fonts
  all work), using `tnum`+`lnum` tabular figures for anything numeric.
- **Shadow** neutral only, reserved for genuinely floating layers.

## Rules this UI should pass (self-audit before "done")

The five sins: (1) no low-contrast text on the accent color (use the accent-ink token); (2) no accent
in any shadow/glow; (3) no accent-tinted "neutral" canvas; (4) no approximate placement (flex/grid
anchored, not fragile utilities); (5) no hue-only status (dot+label always). Plus: one accent · one
primary action per view · hierarchy by type before chrome · hairlines before shadows · lead with one
number, never a uniform 3-to-5-up stat-tile grid · numeric columns right-aligned + tabular · no
gradients-as-chrome, no glassmorphism, no em-dashes in shipped copy.

## Table law (read this before touching `tracker.html`)

A tracker that grows past a handful of rows fails in a very specific way if you don't guard against
it: one long free-text cell blows out the row height and crushes every other column. Five rules stop
that:

1. **A table cell holds a fact, never a paragraph.** Any "next action"-style field is a short
   imperative, verb-first, hard cap ~80 characters, clamped to two lines. Anything longer goes in a
   `notes` field, revealed only in the expanded row.
2. **`table-layout: fixed` with an explicit `<colgroup>`, always.** A column must never be crushed by
   another column's content.
3. **Detail on demand, not detail in the grid.** Long-form context lives in a **disclosure row** (a
   real `<button>` with `aria-expanded` + `aria-controls`, ≥28px hit area, instant, no height
   animation). Never a modal for this.
4. **The detail panel must not repeat what the row already shows.** It carries only what the row
   cannot.
5. **No column whose value is identical on most rows.** If a signal is rare, put it in the drawer, not
   a column that reads the same thing on 90% of rows.

Corollaries: numeric columns right-aligned + tabular · a missing value renders as an em-dash glyph,
never a fake zero · sticky header · hairline rows, never zebra.

## Motion: frequency-gated

A tracker you look at often deserves speed over animation: everything instant, including row
disclosure (no height transition, no chevron easing). One reasonable exception: a slow live-status
pulse (2-3s) on in-progress rows, respecting `prefers-reduced-motion`. No hover animations that shift
weight/size.

## Accessibility floor

Native controls (`button`, `input`) · visible `:focus-visible` ring (≥2px) · sortable headers are real
buttons with `aria-sort` + accessible names · every control has an accessible name · hit targets
≥24px · input font ≥16px (avoids iOS zoom).

## Verification

Verify in a real browser, not a preview window; test each state by using it. A change that isn't
visible didn't happen.

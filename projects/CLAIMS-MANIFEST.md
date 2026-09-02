# CLAIMS-MANIFEST: what each published case-study route actually supports

**Machine-read by `scripts/verify_claims.py` R10 (LINK-CLAIM).** For each case study you publish
on your own portfolio, a claim placed next to its link must be true ABOUT THAT LINK, not just true
about your career in general. A career-true claim next to a link that shows none of it is still a
false claim about the link. R10 exists to catch exactly that gap before it reaches a real reader.

**`domain:`** below is your own portfolio's domain, read at runtime by `verify_claims.py`. Nothing
in the script hardcodes a domain. Replace the placeholder with your real one. If this line is
missing, or this whole file is missing, R10 simply finds no links to check (fails safe, never
fails loud on your behalf).

domain: example.com

**Format contract (R10 parses this):** one `## <slug>` section per published route. Fields:
- `slug:` is the path segment after your `domain:` (so `example.com/<slug>`).
- `aliases:` are other path segments that resolve to the same route (optional, comma-separated).
- `source-of-truth:` is where the deployed page's real source lives in this repo.
- `scope-line:` is the artifact's own stated scope, quoted verbatim (folded into the shows haystack).
- `shows:` are generous keywords the published artifact genuinely presents (repeatable, comma-separated).
  A distinctive work-claim noun sitting next to the link must appear here, or R10 goes AMBER.
- `never-claim-here:` lists terms that may NEVER appear in a block/entry that also links this route
  (repeatable, comma-separated; matched as normalized substrings). Any hit is RED.
- `check: link-only` means the route is real but carries no claim scope (no shows/never enforcement
  beyond recognizing the slug).

A `<domain>/<slug>` whose slug has no section here is RED, which forces you to keep this file
current the moment a new case study goes live, rather than letting a dead or unknown link ship
silently. Keep terms lowercase; matching is substring-on-normalized-text.

This file ships with ONE placeholder section below so the gate has something to validate itself
against on a fresh clone (`scripts/verify_claims.py --selftest` reads it). Replace it with your own
published routes, and delete the placeholder once you have real ones.

---

## example-case-study

slug: example-case-study
url: https://example.com/example-case-study/
source-of-truth: projects/example-case-study/index.html
scope-line: "A placeholder route used only by the selftest fixture. Replace with your own case study."
shows: design system, tokens, component library work
never-claim-here: solo founder, sole engineer, i built the entire product alone
notes: PLACEHOLDER. Replace this section with a real published route once you have one. The
  selftest fixture (`applications/EXAMPLE-fixture-selftest/`) exercises R10 against this exact
  section, so keep its slug and terms in sync with `scripts/verify_claims.py` if you rename it.

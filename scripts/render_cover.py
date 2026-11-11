#!/usr/bin/env python3
"""render_cover.py: put a dossier's cover-note.md body into its cover-letter.html and render the one-page PDF.

The body is the text between the first two '---' lines of cover-letter/cover-note.md (the sendable letter, written
per knowledge-base/17-writing.md). The first paragraph ("Hi ...,") becomes the salutation, a closing paragraph
("Thanks," plus your name) the signoff, and every other paragraph a <p>. A dossier without a cover-letter.html gets
applications/TEMPLATE-company-role/cover-letter/cover-letter.html and its fonts. The page header (your name, title and
contact line) is filled from knowledge-base/12 sections 1 and 2 and knowledge-base/07 while it still holds the
template's placeholders; a contact item you have not recorded is left out.

Needs weasyprint (python3 -m pip install weasyprint). pdfinfo is used for the page count when it is installed.

Usage:
    python3 scripts/render_cover.py applications/<dossier> [--meta "Company, Role, City, ST"]
    python3 scripts/render_cover.py --selftest
Exit 0 = rendered, one page; 1 = a problem (printed, with what to fix); 3 = rendered but the page count could not be read.
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO / "applications/TEMPLATE-company-role/cover-letter"
KB12 = REPO / "knowledge-base/12-application-answers.md"
KB07 = REPO / "knowledge-base/07-master-resume.md"
MIDDOT = " &nbsp;&middot;&nbsp; "

CLOSING = re.compile(r"^(thanks|thank you|many thanks|best|best regards|kind regards|warm regards|regards|sincerely|cheers|talk soon|yours)\s*[,.!]?$", re.I)
UNFILLED = re.compile(r"\[[^\]]*\]")


def body_of(note: Path) -> str:
    parts = re.split(r"^---\s*$", note.read_text(errors="ignore"), flags=re.M)
    return parts[1].strip() if len(parts) >= 3 else ""


def _cell(md: str, field: str) -> str:
    """A '| field | value |' row's value, '' while it is still a placeholder."""
    m = re.search(r"^\|\s*" + re.escape(field) + r"\s*\|\s*(.*?)\s*\|\s*$", md, re.M | re.I)
    v = m.group(1).strip() if m else ""
    return "" if not v or v.startswith("[") else v


def read_profile(kb12: str, kb07: str) -> dict:
    """Your header details from the knowledge base. Missing ones stay ''."""
    kb12 = re.sub(r"<!--.*?-->", "", kb12, flags=re.S)
    kb07 = re.sub(r"<!--.*?-->", "", kb07, flags=re.S)

    def exact(key):
        m = re.search(r"^exact:\s*" + key + r"\s*\|\s*(.+)$", kb07, re.M)
        v = m.group(1).strip() if m else ""
        return "" if v.startswith("[") else v

    name = " ".join(x for x in (_cell(kb12, "First name"), _cell(kb12, "Last name")) if x)
    city = re.sub(r",\s*[A-Za-z ]*\b(time|standard)\b.*$", "", _cell(kb12, "City and time zone"), flags=re.I).strip()
    return {"name": name, "title": exact("title"), "email": _cell(kb12, "Email") or exact("email"), "phone": _cell(kb12, "Phone"),
            "site": _cell(kb12, "Portfolio / personal site") or exact("portfolio"), "linkedin": _cell(kb12, "LinkedIn") or exact("linkedin"), "city": city}


def _short(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def _href(url: str) -> str:
    return url if re.match(r"^https?://", url) else "https://" + url


def fill_header(src: str, p: dict) -> str:
    sep = ' <span class="sep">|</span>\n  '
    items = []
    if p["phone"]:
        items.append(html.escape(p["phone"]))
    if p["email"]:
        items.append(f'<a href="mailto:{html.escape(p["email"])}">{html.escape(p["email"])}</a>')
    for u in (p["site"], p["linkedin"]):
        if u:
            items.append(f'<a href="{html.escape(_href(u))}">{html.escape(_short(u))}</a>')
    src = re.sub(r'<div class="name">.*?</div>', lambda m: f'<div class="name">{html.escape(p["name"])}</div>', src, count=1, flags=re.S)
    src = re.sub(r'<div class="tagline">.*?</div>\n?', lambda m: f'<div class="tagline">{html.escape(p["title"])}</div>\n' if p["title"] else "", src, count=1, flags=re.S)
    src = re.sub(r'<div class="contact where">.*?</div>\n?', lambda m: f'<div class="contact where">{html.escape(p["city"])}</div>\n' if p["city"] else "", src, count=1, flags=re.S)
    src = re.sub(r'<div class="contact">.*?</div>', lambda m: '<div class="contact">\n  ' + sep.join(items) + "\n</div>", src, count=1, flags=re.S)
    return src


def to_html(body: str, name: str, site: str = "") -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paras or not re.match(r"^(Hi|Hello|Dear)\b", paras[0]):
        raise ValueError("the letter must open with its greeting line (Hi ...,)")
    sal, rest = paras[0], paras[1:]
    closing, signer = "Thanks,", name
    if rest:
        lines = [l.strip() for l in rest[-1].splitlines() if l.strip()]
        words = rest[-1].split()
        if len(words) <= 7:
            if len(lines) == 2 and CLOSING.match(lines[0]):
                closing, signer = lines[0], lines[1]
                rest.pop()
            elif len(lines) == 1:
                m = re.match(r"^(.+?[,.!])\s+(\S.*)$", lines[0])
                if m and CLOSING.match(m.group(1)):
                    closing, signer = m.group(1), m.group(2)
                    rest.pop()
                elif name and lines[0].rstrip(".") == name:
                    signer = name
                    rest.pop()
                    if rest and CLOSING.match(rest[-1]):
                        closing = rest.pop()
                    else:
                        closing = ""
                elif CLOSING.match(lines[0]):
                    closing = rest.pop()
    if not signer:
        raise ValueError("no name to sign with: fill in First name and Last name in knowledge-base/12 section 1, or end the letter with your name")
    host = re.escape(_short(site)) if site else ""

    def esc(t: str) -> str:
        t = html.escape(" ".join(t.split()), quote=False)
        t = re.sub(r"https?://[^\s<]+[^\s<.,)]", lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', t)
        if host:
            t = re.sub(r"(?<![/\w.\">])" + host + r"(?![\w/])", lambda m: f'<a href="{_href(m.group(0))}">{m.group(0)}</a>', t)
        return t

    out = [f'<p class="salutation">{esc(sal)}</p>', ""]
    for p in rest:
        out += [f"<p>{esc(p)}</p>", ""]
    out.append(f'<p class="signoff">{html.escape(closing) + "<br>" if closing else ""}{html.escape(signer)}</p>')
    return "\n".join(out)


def build_page(src: str, body: str, profile: dict, meta) -> str:
    """The finished HTML. Raises ValueError, with what to fix, on anything that would ship a placeholder."""
    if UNFILLED.search(body):
        raise ValueError("cover-note.md still holds a [placeholder]: " + UNFILLED.search(body).group(0)[:60])
    if ">Your Name<" in src:
        if not profile["name"]:
            raise ValueError("no name for the letterhead: fill in First name and Last name in knowledge-base/12 section 1 (or run /setup)")
        src = fill_header(src, profile)
    if meta:
        safe = MIDDOT.join(html.escape(x.strip()) for x in re.split(r"\s*[·,]\s*", meta, maxsplit=2))
        src = re.sub(r'<div class="meta">.*?</div>', lambda m: f'<div class="meta">{safe}</div>', src, count=1, flags=re.S)
    elif re.search(r'<div class="meta">\s*Company\b', src):
        raise ValueError('this letter has no company line yet: pass --meta "Company, Role, City, ST"')
    letter = to_html(body, profile["name"], profile["site"])
    new, n = re.subn(r'<p class="salutation">.*<p class="signoff">.*?</p>', lambda m: letter, src, flags=re.S)
    if n != 1:
        raise ValueError('could not find the <p class="salutation"> .. <p class="signoff"> block in cover-letter.html')
    return new


def page_count(pdf: Path):
    if shutil.which("pdfinfo"):
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        if m:
            return int(m.group(1))
    n = len(re.findall(rb"/Type\s*/Page\b", pdf.read_bytes()))
    return n or None


def render(page: Path, pdf: Path):
    """None on success, or the error text."""
    cmd = ["weasyprint"] if shutil.which("weasyprint") else [sys.executable, "-m", "weasyprint"]
    r = subprocess.run(cmd + [str(page), str(pdf)], capture_output=True, text=True)
    if r.returncode != 0 or not pdf.exists():
        return r.stderr[-400:] or "weasyprint did not produce a PDF"
    return None


def main(argv) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 2 or argv[1].startswith("--"):
        print(__doc__)
        return 1
    d = Path(argv[1])
    d = d if d.is_absolute() else REPO / d
    meta = argv[argv.index("--meta") + 1] if "--meta" in argv and argv.index("--meta") + 1 < len(argv) else None
    cl = d / "cover-letter"
    note = cl / "cover-note.md"
    if not note.exists():
        print(f"render_cover: no {note}")
        return 1
    body = body_of(note)
    if not body:
        print("render_cover: cover-note.md has no body between its first two '---' lines")
        return 1
    page = cl / "cover-letter.html"
    profile = read_profile(KB12.read_text(errors="ignore") if KB12.exists() else "", KB07.read_text(errors="ignore") if KB07.exists() else "")
    template = TEMPLATE_DIR / "cover-letter.html"
    if not page.exists() and not template.exists():
        print(f"render_cover: no cover-letter.html here and no template at {template}")
        return 1
    src = page.read_text() if page.exists() else template.read_text()
    try:
        new = build_page(src, body, profile, meta)
    except ValueError as e:
        print(f"render_cover: {e}")
        return 1
    if not (cl / "fonts").exists() and (TEMPLATE_DIR / "fonts").exists():
        shutil.copytree(TEMPLATE_DIR / "fonts", cl / "fonts")
    page.write_text(new)
    signer = re.search(r'<div class="name">(.*?)</div>', new, re.S)
    who = html.unescape(signer.group(1)).strip() if signer else profile["name"]
    pdf = cl / f"{who} - Cover Letter.pdf"
    err = render(page, pdf)
    if err:
        print("render_cover: weasyprint failed (install it with: python3 -m pip install weasyprint): " + err)
        return 1
    pages = page_count(pdf)
    if pages is None:
        print(f"render_cover: {pdf} rendered, but its page count could not be read. NOT CHECKED: rasterize it and look.")
        return 3
    if pages != 1:
        print(f"render_cover: the PDF has {pages} pages; the letter must fit one page. Cut a paragraph and run this again.")
        return 1
    print(f"render_cover: {pdf} rendered, 1 page, {pdf.stat().st_size} bytes")
    return 0


SAMPLE = """<!doctype html><style>@page { size: A4; margin: 0.75in 1in; } .name{font-weight:700}</style>
<div class="name">Your Name</div>
<div class="tagline">Your Title<br>A one-line description</div>
<div class="contact">
  +1 (555) 555-5555 <span class="sep">|</span>
  <a href="mailto:you@example.com">you@example.com</a>
</div>
<div class="contact where">City, State</div>
<hr>
<div class="meta">Company &nbsp;&middot;&nbsp; Role &nbsp;&middot;&nbsp; Location</div>
<p class="salutation">Hi,</p>
<p>[Paragraph 1]</p>
<p class="signoff">Thanks,<br>Your name</p>
"""
KB12_FILLED = "| First name | Jordan |\n| Last name | Rivera |\n| Email | jordan@example.com |\n| Phone | [ ] |\n| Portfolio / personal site | https://example.org/jordan |\n| LinkedIn | [ ] |\n| City and time zone | Dayton, OH, Central Time |\n"
KB07_FILLED = "```canonical-facts\nexact: title | Registered Nurse\n```\n"
KB12_BLANK = "| First name | [ ] |\n| Last name | [ ] |\n| Email | [ ] |\n"
BODY = "Hi Sam,\n\nYour clinic in Dayton is hiring for nights.\n\nMy work is at example.org/jordan and https://example.org/more, if useful.\n\nThanks,\nJordan Rivera"


def selftest() -> int:
    ok = True

    def expect(name, cond):
        nonlocal ok
        if not cond:
            ok = False
            print("SELFTEST FAIL:", name)

    def raises(fn):
        try:
            fn()
        except ValueError as e:
            return str(e)
        return ""

    p = read_profile(KB12_FILLED, KB07_FILLED)
    expect("profile read", p["name"] == "Jordan Rivera" and p["title"] == "Registered Nurse" and p["phone"] == "" and p["city"] == "Dayton, OH")
    out = build_page(SAMPLE, BODY, p, "Acme Clinic, Night Nurse, Dayton, OH")
    expect("letterhead filled", ">Jordan Rivera<" in out and "Registered Nurse" in out and "you@example.com" not in out and "555-5555" not in out)
    expect("the placeholder paragraph is gone", "[Paragraph" not in out and "Your name" not in out)
    expect("the closing is the note's own", "Thanks,<br>Jordan Rivera" in out and out.count('class="signoff"') == 1)
    expect("meta filled", "Acme Clinic" in out and "Night Nurse" in out and ">Company" not in out)
    expect("an unrecorded contact item is left out", "linkedin" not in out.lower())
    expect("the user's own site and any full URL are linked", 'href="https://example.org/more"' in out and 'href="https://example.org/jordan"' in out)
    expect("a salutation is required", "greeting" in raises(lambda: to_html("Your clinic is hiring.\n\nThanks,\nSam Lee", "Sam Lee")))
    expect("a name-only last paragraph signs without a closing", '<p class="signoff">Sam Lee</p>' in to_html("Hi,\n\nA line.\n\nSam Lee", "Sam Lee"))
    expect("a closing with no name uses the recorded name", 'Best,<br>Sam Lee' in to_html("Hi,\n\nA line.\n\nBest,", "Sam Lee"))
    expect("no name anywhere is refused, with the fix", "knowledge-base/12" in raises(lambda: build_page(SAMPLE, BODY, read_profile(KB12_BLANK, ""), "A, B, C")))
    expect("a template note is refused", "placeholder" in raises(lambda: build_page(SAMPLE, "Hi,\n\n[Paragraph 1 goes here]\n\n[Your name]", p, "A, B, C")))
    expect("a missing company line is refused, with the fix", "--meta" in raises(lambda: build_page(SAMPLE, BODY, p, None)))
    expect("no owner of this script is hard-coded in the signoff", "Thanks,<br>Sam Lee" in to_html("Hi,\n\nA line.", "Sam Lee"))
    if shutil.which("weasyprint") or subprocess.run([sys.executable, "-c", "import weasyprint"], capture_output=True).returncode == 0:
        with tempfile.TemporaryDirectory() as td:
            page, pdf = Path(td) / "c.html", Path(td) / "c.pdf"
            page.write_text(out)
            err = render(page, pdf)
            if err is not None or not pdf.is_file():
                # installed is not working: a weasyprint missing its system libraries is a skip, not a crash
                print(f"  render skipped (weasyprint is installed but did not render: {str(err).strip()[-120:]})")
            else:
                expect("a short letter is one page", page_count(pdf) == 1)
    else:
        print("  render skipped (weasyprint not installed)")
    print("render_cover selftest", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

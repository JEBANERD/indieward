"""Build the IndieWard guide site: plain HTML + one CSS file, no scripts, no trackers.

    python site/build.py [--out site/dist]

Pages come from README.md, docs/creator-guide.md and docs/spec/iw-mark-v1.md.
Links between those pages become links between site pages; links to other repo
files go to GitHub; every outside link (including each legal source) is kept as is.
Needs markdown-it-py (MIT): pip install -e ".[site]".
"""
from __future__ import annotations

import argparse
import html
import posixpath
import re
import shutil
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/JEBANERD/indieward"
# (source, output page, nav label)
PAGES = [
    ("README.md", "index.html", "Home"),
    ("docs/creator-guide.md", "guide.html", "Creator guide"),
    ("docs/spec/iw-mark-v1.md", "spec.html", "IW-Mark spec"),
]
PAGE_FOR = {src: out for src, out, _ in PAGES}
# No scripts, no third-party requests: everything the page loads comes from the site itself.
CSP = "default-src 'none'; style-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site">
<a class="brand" href="index.html">IndieWard</a>
<nav>{nav}</nav>
</header>
<main>
{body}
</main>
<footer class="site">
<p>IndieWard is free and open source (MIT). Not legal advice. Source: <a href="{repo}">{repo_short}</a>.
This page is built from <a href="{src_url}">{src}</a>.</p>
</footer>
</body>
</html>
"""


def _md() -> MarkdownIt:
    # html=False: raw HTML in the docs is shown as text, never injected.
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def rewrite_link(href: str, src: str) -> str:
    """Map a link found in `src` to where it should point on the site."""
    if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", href) or href.startswith(("#", "//")):
        return href  # outside links (legal sources included) and anchors stay exactly as written
    path, _, frag = href.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(src), path)) if path else src
    if target in PAGE_FOR:
        return PAGE_FOR[target] + (f"#{frag}" if frag else "")
    kind = "tree" if (ROOT / target).is_dir() else "blob"
    return f"{REPO_URL}/{kind}/main/{target}" + (f"#{frag}" if frag else "")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render(src: str) -> tuple[str, str]:
    """(page title, body HTML) for one source file."""
    md = _md()
    tokens = md.parse((ROOT / src).read_text(encoding="utf-8"))
    title, seen = None, set()
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            text = tokens[i + 1].content
            title = title or text
            slug = base = _slug(text) or "section"
            n = 2
            while slug in seen:
                slug, n = f"{base}-{n}", n + 1
            seen.add(slug)
            tok.attrSet("id", slug)
        for child in tok.children or []:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                new = rewrite_link(href, src)
                child.attrSet("href", new)
                if new.startswith(("http://", "https://")):
                    child.attrSet("rel", "noopener noreferrer")
    return title or src, md.renderer.render(tokens, md.options, {})


def build(out: Path) -> list[Path]:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy2(Path(__file__).with_name("style.css"), out / "style.css")
    written = [out / "style.css"]
    for src, page, _ in PAGES:
        title, body = render(src)
        current = ' aria-current="page"'
        nav = " ".join(f'<a href="{p}"{current if p == page else ""}>{html.escape(label)}</a>'
                       for _, p, label in PAGES)
        doc = TEMPLATE.format(csp=CSP, title=html.escape(f"{title} | IndieWard" if page != "index.html" else title),
                              nav=nav, body=body, repo=REPO_URL, repo_short=REPO_URL.removeprefix("https://"),
                              src=src, src_url=f"{REPO_URL}/blob/main/{src}")
        (out / page).write_text(doc, encoding="utf-8")
        written.append(out / page)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "site" / "dist"))
    for p in build(Path(ap.parse_args(argv).out)):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

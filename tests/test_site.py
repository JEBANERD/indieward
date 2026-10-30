"""The guide site (site/build.py): builds, no scripts or trackers, every legal source link kept."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("markdown_it")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
build = importlib.util.module_from_spec(spec)
sys.modules["site_build"] = build
spec.loader.exec_module(build)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build.build(out)
    return out


def test_pages_built(site):
    for name in ("index.html", "guide.html", "spec.html", "style.css"):
        assert (site / name).stat().st_size > 0
    assert "Creator guide" in (site / "guide.html").read_text()


def test_no_scripts_trackers_or_outside_loads(site):
    for page in site.glob("*.html"):
        doc = page.read_text()
        assert not re.search(r"(?i)<\s*(script|iframe|object|embed|img)\b", doc), page.name
        assert 'http-equiv="Content-Security-Policy"' in doc and "default-src 'none'" in doc
        # anything the browser loads by itself (stylesheets, icons) must be local
        for m in re.finditer(r'<link\b[^>]*href="([^"]+)"', doc):
            assert not re.match(r"(?i)^(https?:)?//", m.group(1)), (page.name, m.group(1))
        assert not re.search(r"(?i)analytics|googletagmanager|gtag\(|plausible|matomo|cloudflareinsights", doc)
    assert not re.search(r"(?i)@import|url\(\s*['\"]?https?:", (site / "style.css").read_text())


def test_every_outside_link_kept(site):
    for src, page, _ in build.PAGES:
        md_links = set(re.findall(r"\]\((https?://[^)\s]+)\)", (ROOT / src).read_text()))
        html = (site / page).read_text()
        for url in md_links:
            assert f'href="{url}"' in html, (src, url)


def test_internal_links_resolve(site):
    for page in site.glob("*.html"):
        for href in re.findall(r'href="([^"]+)"', page.read_text()):
            if re.match(r"(?i)^[a-z]+:", href) or href.startswith("#"):
                continue
            target, _, frag = href.partition("#")
            assert (site / target).exists(), (page.name, href)
            if frag:
                assert f'id="{frag}"' in (site / target).read_text(), (page.name, href)


def test_rewrite_link():
    rl = build.rewrite_link
    assert rl("docs/creator-guide.md", "README.md") == "guide.html"
    assert rl("spec/iw-mark-v1.md#payload", "docs/creator-guide.md") == "spec.html#payload"
    assert rl("../README.md", "docs/creator-guide.md") == "index.html"
    assert rl("plugin/README.md", "README.md") == f"{build.REPO_URL}/blob/main/plugin/README.md"
    assert rl("plugin/", "README.md") == f"{build.REPO_URL}/tree/main/plugin"
    assert rl("https://www.copyright.gov/registration/", "docs/creator-guide.md") == \
        "https://www.copyright.gov/registration/"
    assert rl("#step-2", "README.md") == "#step-2"


def test_raw_html_in_docs_is_escaped():
    out = build._md().render("Hi <script>alert(1)</script> <img src=x onerror=y>")
    assert "<script" not in out and "<img" not in out and "&lt;script" in out

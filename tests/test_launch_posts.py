"""Launch post drafts (docs/launch): short, honest about the limits first, no overclaims."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

LAUNCH = Path(__file__).resolve().parents[1] / "docs" / "launch"
POSTS = ["itch-devlog.md", "reddit-gamedev.md", "reddit-indiedev.md", "discord.md", "faq.md"]
OVERCLAIMS = re.compile(r"(?i)\b(blocks? (ai|cloning|copying|rippers?)|prevents? (copying|cloning|ripping)|"
                        r"stops? (clones|cloners|copying)|detects? (ai|whether an ai)|guarantee[sd]?|"
                        r"undetectable|unremovable|can't be removed|legal(ly)? (proof|binding))\b")


@pytest.mark.parametrize("name", POSTS)
def test_post_is_short_honest_and_complete(name):
    text = (LAUNCH / name).read_text("utf-8")
    assert len(text.split()) < 300, name
    assert "Not posted" in text.splitlines()[0]
    assert "[TIP JAR LINK]" in text and "pipx install" in text and "indieward doctor" in text
    # the limits come before the features
    first_limit = min(i for i in (text.find("can't"), text.find("Can it stop")) if i >= 0)
    first_feature = min(i for i in (text.find(w) for w in ("atermark", "ertificate", "rap marker", "drafts"))
                        if i >= 0)
    assert 0 <= first_limit < first_feature, name
    assert "AI" in text[:first_feature]
    for m in OVERCLAIMS.finditer(text):
        before = text[max(0, m.start() - 40):m.start()].lower()
        assert re.search(r"(can't|cannot|doesn't|no tool|nothing|never|not)\b", before), (name, m.group(0))

"""P3-04: launch drafts stay short, lead with the limits and keep the honesty lines."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

LAUNCH = Path(__file__).resolve().parents[1] / "docs" / "launch"
DRAFTS = ["itch-devlog.md", "reddit-gamedev.md", "reddit-indiedev.md", "discord.md", "faq.md"]


def _text(name: str) -> str:
    return re.sub(r"<!--.*?-->", "", (LAUNCH / name).read_text(encoding="utf-8"), flags=re.S)


@pytest.mark.parametrize("name", DRAFTS)
def test_draft_is_short_and_leads_with_limits(name):
    t = _text(name)
    assert len(t.split()) < 300
    low = t.lower()
    limit = min(i for i in (low.find("can't stop"), low.find("can't do"), low.find("no tool can stop"),
                            low.find("can't stop anyone"), low.find("nothing stops"),
                            low.find("can indieward stop")) if i >= 0)
    assert limit < low.find("pipx install") if "pipx install" in low else True
    assert limit < len(low) // 3  # the limits come first
    assert "not legal advice" in low or "legal advice?" in low
    assert "Draft" in (LAUNCH / name).read_text(encoding="utf-8").splitlines()[0]  # marked as unposted


@pytest.mark.parametrize("name", ["itch-devlog.md", "reddit-indiedev.md", "discord.md", "faq.md"])
def test_tip_jar_is_a_placeholder(name):
    assert "[TIP JAR LINK]" in _text(name)

"""Machine-readable AI-use reservations. These are SIGNALS, not blocks.

Honored only by crawlers and companies that choose to honor them, mostly at
crawl or training time. None of them stops someone from uploading your
footage to an AI tool. In the EU, a machine-readable opt-out has legal weight
for text-and-data mining (DSM Directive Art. 4(3), AI Act Art. 53(1)(c)); in
the US it doesn't.
"""
from __future__ import annotations

import json

AI_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ClaudeBot", "anthropic-ai", "Google-Extended", "Applebot-Extended",
               "CCBot", "meta-externalagent", "Bytespider", "PerplexityBot", "cohere-ai", "Diffbot",
               "Amazonbot", "xAI-Bot"]


def robots_txt() -> str:
    lines = ["# AI training opt-out (a request, not an enforcement mechanism)",
             "# Content-Signal per Cloudflare's Content Signals Policy:",
             "User-agent: *", "Content-Signal: search=yes, ai-train=no, ai-input=no", "Allow: /", ""]
    for bot in AI_CRAWLERS:
        lines += [f"User-agent: {bot}", "Disallow: /", ""]
    return "\n".join(lines)


def cawg_training_mining() -> str:
    """CAWG training-and-data-mining assertion (v1.1) for C2PA manifests."""
    return json.dumps({
        "label": "cawg.training-mining",
        "data": {"entries": {
            "cawg.ai_inference": {"use": "notAllowed"},
            "cawg.ai_generative_training": {"use": "notAllowed"},
            "cawg.ai_training": {"use": "notAllowed"},
            "cawg.data_mining": {"use": "notAllowed"},
        }},
    }, indent=2)


def tdm_rep_header() -> str:
    """TDM Reservation Protocol (W3C community group) HTTP headers."""
    return "tdm-reservation: 1\n"

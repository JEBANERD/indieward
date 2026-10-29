"""Where each store takes IP notices, pulled from official pages.

Never guess an address. Every entry cites the page it came from and when it
was last checked. Re-check before you file: stores change these.
"""
from __future__ import annotations

LAST_CHECKED = "2026-10-28"

STORES = {
    "steam": {
        "name": "Steam (Valve)",
        "copyright": {"channel": "web_form", "form_url": "https://steamcommunity.com/dmca/create/",
                      "email": None},
        "trademark": {"channel": "web_form", "form_url": "https://steamcommunity.com/dmca/create/",
                      "email": None,
                      "note": "No separate trademark channel was confirmed. Use the same form and say the claim is "
                              "trademark, or ask a lawyer."},
        "sources": ["https://store.steampowered.com/legal/dmca", "https://steamcommunity.com/dmca/create/"],
        "notes": [
            "Steam takes copyright notices through its web form, not email. The .eml in this package is "
            "addressed to you, as a record of exactly what you filed.",
            "The form warns that misrepresenting infringement can make you liable for damages under 17 U.S.C. "
            "512(f), and that notices may be shared with third parties or made public.",
            "Valve suggests adding a notice to your original work's page, e.g. 'Copyright 2026 <owner>. Not "
            "authorized for Steam except under the account ___', which speeds up review.",
        ],
        "verified": "official page",
    },
    "itch": {
        "name": "itch.io",
        "copyright": {"channel": "email", "email": "support@itch.io"},
        "trademark": {"channel": "email", "email": "support@itch.io",
                      "note": "No separate trademark address is published; itch.io handles notices through support."},
        "sources": ["https://itch.io/docs/legal/terms#6-digital-millennium-copyright-act",
                    "https://itch.io/takedowns"],
        "notes": [
            "itch.io's Terms (section 6, Digital Millennium Copyright Act) direct notices to support@itch.io; "
            "notices itch.io publishes at itch.io/takedowns show them arriving there.",
            "itch.io publishes takedown notices it receives, with contact details redacted. Write it as if the "
            "public will read it.",
        ],
        "verified": "official page (terms) + itch.io takedown archive",
    },
    "roblox": {
        "name": "Roblox",
        "copyright": {"channel": "email_or_form", "email": "copyright_agent@roblox.com",
                      "form_url": "https://create.roblox.com/docs/production/publishing/rights-manager",
                      "mail": "Legal, Roblox Corporation, 3150 S. Delaware St., San Mateo, CA 94403",
                      "phone": "(888) 858-2569"},
        "trademark": {"channel": "email_or_form", "email": "trademark_agent@roblox.com",
                      "form_url": "https://create.roblox.com/docs/production/publishing/rights-manager",
                      "mail": "Legal, Roblox Corporation, 3150 S. Delaware St., San Mateo, CA 94403"},
        "sources": ["https://create.roblox.com/docs/production/publishing/ip-guidelines",
                    "https://create.roblox.com/docs/production/publishing/rights-manager"],
        "notes": [
            "The form_url is Roblox's Rights Manager guide; the form itself is in Creator Hub > Intellectual Property.",
            "Rights Manager (Creator Hub > Intellectual Property) is Roblox's streamlined option for users over 18 "
            "and requires one-time ID verification. Email works too.",
        ],
        "verified": "official page",
    },
}


def channel(store: str, kind: str = "copyright") -> dict:
    s = STORES[store]
    return {"store": store, "name": s["name"], **s[kind], "sources": s["sources"], "notes": s["notes"],
            "last_checked": LAST_CHECKED}

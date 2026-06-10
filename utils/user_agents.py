# utils/user_agents.py
# ─────────────────────────────────────────────────────────────
# Realistic browser User-Agent strings for rotation.
# Using a single UA for thousands of requests is a red flag to
# bot detection systems. Rotating through real browser UAs
# makes your traffic look more like organic visitors.
#
# Best practice: use UAs that match real browser market share
# (Chrome ~65%, Firefox ~4%, Safari ~19%). Don't use rare or
# fake UAs — they stand out more than a repeated one.
# ─────────────────────────────────────────────────────────────

import random

# Sourced from real browser releases (Chrome, Firefox, Safari, Edge)
USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome (Linux)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def get_random_ua() -> str:
    """Return a randomly chosen User-Agent string."""
    return random.choice(USER_AGENTS)


def get_weighted_ua() -> str:
    """
    Return a UA weighted by real-world browser market share:
    Chrome ~65%, Safari ~19%, Edge ~5%, Firefox ~4%, others ~7%.
    """
    weights = [
        7,   # Chrome Windows 124
        6,   # Chrome Windows 123
        5,   # Chrome Windows 122
        7,   # Chrome macOS 124
        6,   # Chrome macOS 123
        3,   # Firefox Windows 125
        2,   # Firefox Windows 124
        2,   # Firefox macOS
        8,   # Safari macOS 17.4.1
        6,   # Safari macOS 17.4.1 (13)
        4,   # Edge Windows
        4,   # Chrome Linux
    ]
    return random.choices(USER_AGENTS, weights=weights, k=1)[0]

#!/usr/bin/env python3
"""
scripts/smoke_test_rss.py
=========================
Issue 4 smoke test — proves the RSS adapter works against real-world feeds.

Feeds tested
------------
- BBC News          http://feeds.bbci.co.uk/news/rss.xml
- Al Jazeera        https://www.aljazeera.com/xml/rss/all.xml

For each feed the script:
  1. Fetches raw XML via fetch_feed() (with retry)
  2. Parses it via parse_xml() + parse_entries()
  3. Prints the first 3 article titles, URLs, and published_at values
  4. Exits non-zero if anything unexpectedly breaks

Run from the project root:
    python3 scripts/smoke_test_rss.py
"""
from __future__ import annotations

import sys

# Ensure src/ is on the path when run from the project root
sys.path.insert(0, "src")

from istina.model.adapters.rss_adapter import fetch_articles

FEEDS = [
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

PREVIEW = 3  # titles to print per feed
SEP = "-" * 72


def main() -> int:
    overall_ok = True

    for url in FEEDS:
        print(SEP)
        print(f"Feed : {url}")

        articles = fetch_articles([url])

        if not articles:
            print("  ✗  No articles returned — feed may be empty or unreachable")
            overall_ok = False
            continue

        print(f"  ✓  {len(articles)} article(s) fetched")
        print(f"\n  First {min(PREVIEW, len(articles))} result(s):\n")

        date_ok = True
        for i, a in enumerate(articles[:PREVIEW], 1):
            print(f"  [{i}] {a.title}")
            print(f"       url         : {a.url}")
            print(f"       source      : {a.source}")
            print(f"       published_at: {a.published_at!r}")

            if a.published_at is not None:
                # Basic sanity: must look like an ISO-8601 UTC string
                if not (a.published_at.endswith("Z") and "T" in a.published_at):
                    print(f"       ✗  published_at format unexpected: {a.published_at!r}")
                    date_ok = False
                else:
                    print("       ✓  published_at is valid ISO-8601 UTC")
            else:
                print("       –  published_at is None (feed entry had no date)")
            print()

        if date_ok:
            print("  ✓  published_at parsing OK")
        else:
            print("  ✗  published_at parsing produced unexpected values")
            overall_ok = False

    print(SEP)
    if overall_ok:
        print("ALL FEEDS OK")
        return 0
    else:
        print("ONE OR MORE FEEDS HAD ISSUES")
        return 1


if __name__ == "__main__":
    sys.exit(main())

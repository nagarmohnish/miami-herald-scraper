"""
Miami Herald Article Scraper
Extracts all articles published in the past 30 days from miamiherald.com
using Google News RSS feeds for discovery and googlenewsdecoder for URL resolution.
"""

import csv
import logging
import re
import time
from datetime import datetime, timedelta

import requests
import feedparser
from googlenewsdecoder import new_decoderv1

# =============================================================================
# Configuration
# =============================================================================

OUTPUT_FILE = "miami_herald_articles.csv"
DAYS_BACK = 30
CUTOFF_DATE = datetime.now() - timedelta(days=DAYS_BACK)

# Multiple Google News RSS queries to maximize article coverage.
# Each returns up to 100 results. Varied queries surface different articles.
RSS_QUERIES = [
    "site:miamiherald.com",
    "site:miamiherald.com news",
    "site:miamiherald.com local",
    "site:miamiherald.com crime",
    "site:miamiherald.com politics",
    "site:miamiherald.com business",
    "site:miamiherald.com sports",
    "site:miamiherald.com miami",
    "site:miamiherald.com florida",
    "site:miamiherald.com immigration",
    "site:miamiherald.com entertainment",
    "site:miamiherald.com opinion",
    "site:miamiherald.com real estate",
    "site:miamiherald.com education",
    "site:miamiherald.com environment",
    "site:miamiherald.com health",
    "site:miamiherald.com dolphins",
    "site:miamiherald.com heat",
    "site:miamiherald.com marlins",
    "site:miamiherald.com college",
    "site:miamiherald.com broward",
    "site:miamiherald.com miami-dade",
    "site:miamiherald.com keys",
    "site:miamiherald.com trump",
    "site:miamiherald.com housing",
    "site:miamiherald.com community",
    "site:miamiherald.com cuba",
    "site:miamiherald.com haiti",
    "site:miamiherald.com technology",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# =============================================================================
# URL Resolution
# =============================================================================


def resolve_google_news_url(google_url):
    """Decode a Google News redirect URL to the actual article URL (no network call)."""
    try:
        result = new_decoderv1(google_url)
        if result.get("status") and result.get("decoded_url"):
            return result["decoded_url"]
    except Exception:
        pass
    return google_url


def normalize_url(url):
    """Normalize URL for deduplication."""
    if not url:
        return ""
    url = re.sub(r"https?://amp\.", "https://www.", url)
    url = url.split("?")[0].split("#")[0].rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


# =============================================================================
# Date Parsing
# =============================================================================


def parse_date(date_str):
    """Parse dates from RSS and other formats."""
    if not date_str:
        return None
    date_str = date_str.strip()

    for fmt in [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
    ]:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue

    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", date_str)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return None


# =============================================================================
# Google News RSS Fetching
# =============================================================================


def fetch_gnews_rss(query):
    """Fetch articles from Google News RSS for a given query."""
    encoded = query.replace(" ", "+")
    url = (
        f"https://news.google.com/rss/search"
        f"?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            logging.warning(f"RSS returned {resp.status_code} for: {query}")
            return []
    except Exception as e:
        logging.warning(f"Failed to fetch RSS for '{query}': {e}")
        return []

    feed = feedparser.parse(resp.text)
    articles = []

    for entry in feed.entries:
        title = entry.get("title", "")
        title = re.sub(r"\s*[-\u2013\u2014]\s*Miami Herald\s*$", "", title).strip()

        pub_date = entry.get("published", "")
        google_url = entry.get("link", "")

        # Google News RSS summaries just repeat the title — no real description available
        summary = ""

        source = ""
        if hasattr(entry, "source") and isinstance(entry.source, dict):
            source = entry.source.get("title", "")

        if source and "Miami Herald" not in source:
            continue

        articles.append({
            "title": title,
            "publish_date": pub_date,
            "google_url": google_url,
            "url": "",
            "author": "",
            "summary": summary,
        })

    return articles


def collect_all_articles():
    """Run all RSS queries and collect unique articles."""
    all_articles = {}

    for i, query in enumerate(RSS_QUERIES):
        logging.info(f"[{i + 1}/{len(RSS_QUERIES)}] Fetching: {query}")
        articles = fetch_gnews_rss(query)
        new = 0
        for article in articles:
            key = article["title"].lower().strip()
            if key and key not in all_articles:
                all_articles[key] = article
                new += 1

        logging.info(f"  Got {len(articles)} results, {new} new (total: {len(all_articles)})")
        time.sleep(1)

    return list(all_articles.values())


# =============================================================================
# URL Resolution Phase
# =============================================================================


def resolve_urls(articles):
    """Resolve Google News URLs to actual Miami Herald URLs (local decode, no network)."""
    logging.info(f"Resolving {len(articles)} article URLs...")
    resolved = 0

    for article in articles:
        real_url = resolve_google_news_url(article["google_url"])

        if "miamiherald.com" in real_url:
            article["url"] = normalize_url(real_url)
            resolved += 1
        else:
            article["url"] = article["google_url"]

    logging.info(f"  Resolved {resolved}/{len(articles)} URLs to miamiherald.com")
    return articles


# =============================================================================
# Filter and Export
# =============================================================================


def filter_by_date(articles):
    """Keep only articles from the past 30 days."""
    filtered = []
    for article in articles:
        dt = parse_date(article["publish_date"])
        if dt is None or dt >= CUTOFF_DATE:
            filtered.append(article)
    removed = len(articles) - len(filtered)
    logging.info(f"Date filter: {len(filtered)} kept, {removed} removed")
    return filtered


def deduplicate_by_url(articles):
    """Final dedup pass by resolved URL."""
    seen = {}
    unique = []
    for article in articles:
        url = normalize_url(article["url"])
        if url not in seen:
            seen[url] = True
            unique.append(article)
    logging.info(f"Dedup: {len(unique)} unique (removed {len(articles) - len(unique)} dupes)")
    return unique


def write_csv(articles, filename):
    """Write articles to CSV sorted by date (most recent first)."""
    fieldnames = ["title", "url", "publish_date", "author", "summary"]
    sorted_articles = sorted(
        articles,
        key=lambda a: parse_date(a.get("publish_date")) or datetime.min,
        reverse=True,
    )

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for article in sorted_articles:
            dt = parse_date(article.get("publish_date"))
            writer.writerow({
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "publish_date": dt.strftime("%Y-%m-%d") if dt else "",
                "author": article.get("author", ""),
                "summary": (article.get("summary", "") or "")[:500],
            })

    logging.info(f"Wrote {len(sorted_articles)} articles to {filename}")


# =============================================================================
# Main
# =============================================================================


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    logging.info("=" * 60)
    logging.info("Miami Herald Article Scraper")
    logging.info(f"Date range: {CUTOFF_DATE.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}")
    logging.info("=" * 60)

    # Phase 1: Discover via Google News RSS
    logging.info("--- Phase 1: Discovering articles ---")
    articles = collect_all_articles()
    logging.info(f"Discovered {len(articles)} unique articles")

    # Phase 2: Filter by date
    logging.info("--- Phase 2: Filtering by date ---")
    articles = filter_by_date(articles)

    # Phase 3: Resolve URLs
    logging.info("--- Phase 3: Resolving URLs ---")
    articles = resolve_urls(articles)

    # Phase 4: Final dedup
    logging.info("--- Phase 4: Deduplication ---")
    articles = deduplicate_by_url(articles)

    # Phase 5: Export
    logging.info("--- Phase 5: Writing CSV ---")
    write_csv(articles, OUTPUT_FILE)

    # Summary
    logging.info("=" * 60)
    logging.info(f"DONE: {len(articles)} articles saved to {OUTPUT_FILE}")
    with_title = sum(1 for a in articles if a.get("title"))
    with_date = sum(1 for a in articles if parse_date(a.get("publish_date")))
    with_url = sum(1 for a in articles if "miamiherald.com" in a.get("url", ""))
    with_author = sum(1 for a in articles if a.get("author"))
    with_summary = sum(1 for a in articles if a.get("summary"))
    logging.info(f"  With title:   {with_title}/{len(articles)}")
    logging.info(f"  With date:    {with_date}/{len(articles)}")
    logging.info(f"  With real URL:{with_url}/{len(articles)}")
    logging.info(f"  With author:  {with_author}/{len(articles)}")
    logging.info(f"  With summary: {with_summary}/{len(articles)}")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()

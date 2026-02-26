# How the Miami Herald Scraper Works

## Problem

Miami Herald's website (miamiherald.com) is protected by Cloudflare and blocks direct programmatic access. This scraper works around that by using **Google News RSS feeds** as an indirect discovery layer.

## Pipeline Overview

The scraper runs in 5 sequential phases:

```
Google News RSS --> Date Filter --> URL Resolution --> Deduplication --> CSV Export
```

### Phase 1: Article Discovery

Google News provides a public RSS endpoint at `news.google.com/rss/search`. By searching `site:miamiherald.com`, the feed returns articles published by the Miami Herald with titles and publish dates.

Each query returns up to 100 results, so the scraper runs **29 topic-specific queries** (news, crime, politics, sports, etc.) to maximize coverage. Articles are deduplicated by title as they're collected. A 1-second delay between requests avoids rate limiting.

### Phase 2: Date Filtering

Articles older than 30 days are removed. The date parser handles multiple formats (RFC 2822, ISO 8601, etc.) since RSS feeds aren't always consistent. Articles with unparseable dates are kept rather than discarded.

### Phase 3: URL Resolution

Google News RSS links point to `news.google.com/rss/articles/...` redirect URLs, not the actual Miami Herald URLs. The `googlenewsdecoder` library decodes the base64-encoded protobuf data in these URLs to extract the real `miamiherald.com` article link. No network call needed for this step.

### Phase 4: Deduplication

After URL resolution, a second dedup pass runs on the resolved URLs. This catches cases where different Google News entries pointed to the same underlying article. URLs are normalized first (strip query params, fragments, convert AMP URLs, enforce HTTPS).

### Phase 5: CSV Export

Articles are sorted by date (most recent first) and written to `miami_herald_articles.csv` with columns: `title`, `url`, `publish_date`, `author`, `summary`.

## Limitations

- **~400-500 articles per run** — limited by Google News RSS returning max 100 results per query
- **No author or summary data** — Google News RSS doesn't include these fields
- **URL resolution can vary** — the decoder occasionally fails for some URLs, falling back to the Google News redirect link

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to Google News RSS |
| `feedparser` | Parse RSS/Atom XML feeds |
| `googlenewsdecoder` | Decode Google News redirect URLs to real article URLs |

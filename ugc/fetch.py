"""Download TikTok videos by profile or hashtag with Apify's TikTok Scraper."""
import os
from pathlib import Path

import requests
from apify_client import ApifyClient

ACTOR = "clockworks/tiktok-scraper"


def fetch(out_dir, profiles=(), hashtags=(), limit=10):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    run = client.actor(ACTOR).call(run_input={
        "profiles": [p.lstrip("@") for p in profiles],
        "hashtags": [h.lstrip("#") for h in hashtags],
        "resultsPerPage": limit,
        "shouldDownloadVideos": True,
    })
    saved = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        urls = item.get("mediaUrls") or []
        if not urls:
            continue
        author = (item.get("authorMeta") or {}).get("name", "unknown")
        path = out_dir / f"{author}_{item['id']}.mp4"
        if path.exists():
            continue
        with requests.get(urls[0], stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        print(f"  saved {path}")
        saved.append(path)
    return saved

#!/usr/bin/env python3
"""
Daily Research Digest — AI, SAP & Science
Fetches RSS feeds directly (no blogwatcher). Runs in GitHub Actions.
Sends to Telegram via bot token + chat ID from environment.
Only includes items published in the last 48 hours.
"""

import os
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

FEEDS = {
    "AI Tools & Models": [
        ("OpenAI Blog",       "https://openai.com/blog/rss.xml"),
        ("Anthropic Blog",    "https://www.anthropic.com/rss.xml"),
        ("DeepMind Blog",     "https://deepmind.google/blog/rss/"),
        ("HuggingFace Blog",  "https://huggingface.co/blog/feed.xml"),
        ("The Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
        ("MIT Tech Review",   "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
        ("VentureBeat AI",    "https://venturebeat.com/category/ai/feed/"),
        ("Ars Technica AI",   "https://feeds.arstechnica.com/arstechnica/technology-lab"),
        ("ArXiv cs.AI",       "https://rss.arxiv.org/rss/cs.AI"),
    ],
    "SAP & Enterprise": [
        ("SAP News",          "https://news.sap.com/feed/"),
        ("Google News SAP",   "https://news.google.com/rss/search?q=SAP+SuccessFactors&hl=en-GB&gl=GB&ceid=GB:en"),
    ],
    "Science & Research": [
        ("Nature",            "https://www.nature.com/nature.rss"),
        ("Science Daily",     "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
        ("ArXiv cs.CL",       "https://rss.arxiv.org/rss/cs.CL"),
    ],
}

PRIORITY_KEYWORDS = [
    "benchmark", "launch", "release", "breakthrough", "beats", "outperforms",
    "SAP", "SuccessFactors", "S/4HANA", "BTP",
    "GPT", "Claude", "Gemini", "Llama", "Mistral", "Qwen",
    "o3", "o4", "reasoning model", "multimodal",
    "Nature", "peer-reviewed", "open source", "open-source", "weights released",
    "agentic", "agent framework", "MCP", "tool use",
]

SAP_KEYWORDS = [
    "sap", "successfactors", "success factors", "s/4hana", "sap btp",
    "hxm", "employee central", "workforce", "payroll", "talent management",
    "hana", "rise with sap",
]

# Only show items published within the last 48 hours
MAX_AGE_HOURS = 48


def parse_date(date_str):
    """Parse RSS/Atom date strings to UTC datetime. Returns None if unparseable."""
    if not date_str:
        return None
    # Try RFC 2822 (RSS pubDate: "Tue, 28 Apr 2026 10:00:00 +0000")
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        pass
    # Try ISO 8601 (Atom published: "2026-04-28T10:00:00Z")
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str[:19], fmt[:len(date_str[:19])])
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def is_recent(item, cutoff):
    """Return True if item has no parseable date (include by default) or is within cutoff."""
    dt = parse_date(item.get("date_raw", ""))
    if dt is None:
        return False  # no date = skip (avoids old undated items)
    return dt >= cutoff


def fetch_feed(url, source_name, timeout=10):
    items = []
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; DailyDigestBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Atom feed
        entries = root.findall(".//atom:entry", ns)
        if not entries:
            # RSS feed
            entries = root.findall(".//item")

        for entry in entries[:15]:  # fetch more, then filter by date
            title = (
                entry.findtext("title") or
                entry.findtext("atom:title", namespaces=ns) or ""
            ).strip()
            link = (
                entry.findtext("link") or
                entry.findtext("atom:link[@rel='alternate']", namespaces=ns) or
                (entry.find("atom:link", ns).get("href") if entry.find("atom:link", ns) is not None else "") or ""
            ).strip()
            pub_raw = (
                entry.findtext("pubDate") or
                entry.findtext("published") or
                entry.findtext("updated") or
                entry.findtext("atom:published", namespaces=ns) or
                entry.findtext("atom:updated", namespaces=ns) or ""
            ).strip()

            if title and link:
                dt = parse_date(pub_raw)
                display_date = dt.strftime("%Y-%m-%d") if dt else pub_raw[:10]
                items.append({
                    "title": title,
                    "url": link,
                    "date": display_date,
                    "date_raw": pub_raw,
                    "source": source_name
                })
    except Exception as e:
        print(f"  [warn] {source_name}: {e}")
    return items


def is_priority(item):
    text = item.get("title", "").lower()
    return any(kw.lower() in text for kw in PRIORITY_KEYWORDS)


def is_sap_relevant(item):
    text = item.get("title", "").lower()
    return any(kw in text for kw in SAP_KEYWORDS)


def build_digest():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    today = now.strftime("%A %d %B %Y")
    sections = []

    cat_emoji = {
        "AI Tools & Models": "🤖",
        "SAP & Enterprise": "🏢",
        "Science & Research": "🔬",
    }

    for cat, feeds in FEEDS.items():
        all_items = []
        for source_name, url in feeds:
            fetched = fetch_feed(url, source_name)
            # Filter by age first
            fetched = [i for i in fetched if is_recent(i, cutoff)]
            if cat == "SAP & Enterprise":
                fetched = [i for i in fetched if is_sap_relevant(i)]
            all_items.extend(fetched)

        # Sort: priority first, then by date desc
        seen = set()
        deduped = []
        for item in sorted(all_items, key=lambda x: (not is_priority(x), x.get("date", ""))):
            key = item["title"][:60].lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        top = deduped[:4]
        if not top:
            emoji = cat_emoji.get(cat, "📌")
            sections.append(f"{emoji} *{cat}*\n_No new items in the last 48 hours._")
            continue

        emoji = cat_emoji.get(cat, "📌")
        lines = [f"{emoji} *{cat}*"]
        for item in top:
            title = item["title"][:90]
            url = item["url"]
            source = item["source"]
            date = item["date"]
            star = " ⭐" if is_priority(item) else ""
            lines.append(f"• [{title}]({url}){star}")
            lines.append(f"  _{source}_ | {date}")
        sections.append("\n".join(lines))

    header = f"📰 *Daily Research Digest*\n_{today}_\n_Last 48 hours only_"
    body = "\n\n".join(sections) if sections else "_No new items found today._"
    return f"{header}\n\n{body}"


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("No Telegram credentials — printing digest:\n")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    if result.get("ok"):
        print(f"Sent to Telegram (message_id={result['result']['message_id']})")
    else:
        print(f"Telegram error: {result}")


if __name__ == "__main__":
    digest = build_digest()
    send_telegram(digest)

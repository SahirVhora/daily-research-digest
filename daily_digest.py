#!/usr/bin/env python3
"""
Daily Research Digest — AI, SAP & Science
Fetches RSS feeds directly (no blogwatcher). Runs in GitHub Actions.
Sends to Telegram via bot token + chat ID from environment.
"""

import os
import re
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

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

        for entry in entries[:8]:
            title = (
                entry.findtext("title") or
                entry.findtext("atom:title", namespaces=ns) or ""
            ).strip()
            link = (
                entry.findtext("link") or
                entry.findtext("atom:link[@rel='alternate']", namespaces=ns) or
                (entry.find("atom:link", ns).get("href") if entry.find("atom:link", ns) is not None else "") or ""
            ).strip()
            pub = (
                entry.findtext("pubDate") or
                entry.findtext("published") or
                entry.findtext("atom:published", namespaces=ns) or ""
            ).strip()
            if title and link:
                items.append({"title": title, "url": link, "date": pub[:16], "source": source_name})
    except Exception:
        pass
    return items


def is_priority(item):
    text = item.get("title", "").lower()
    return any(kw.lower() in text for kw in PRIORITY_KEYWORDS)


def is_sap_relevant(item):
    text = item.get("title", "").lower()
    return any(kw in text for kw in SAP_KEYWORDS)


def build_digest():
    today = datetime.now(timezone.utc).strftime("%A %d %B %Y")
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
            if cat == "SAP & Enterprise":
                fetched = [i for i in fetched if is_sap_relevant(i)]
            all_items.extend(fetched)

        # Sort: priority first, then keep order (dedup by title)
        seen = set()
        deduped = []
        for item in sorted(all_items, key=lambda x: (not is_priority(x), 0)):
            key = item["title"][:60].lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)

        top = deduped[:4]
        if not top:
            continue

        emoji = cat_emoji.get(cat, "📌")
        lines = [f"{emoji} *{cat}*"]
        for item in top:
            title = item["title"][:90]
            url = item["url"]
            source = item["source"]
            date = item["date"][:10] if item["date"] else ""
            star = " ⭐" if is_priority(item) else ""
            lines.append(f"• [{title}]({url}){star}")
            lines.append(f"  _{source}_ | {date}")
        sections.append("\n".join(lines))

    header = f"📰 *Daily Research Digest*\n_{today}_"
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

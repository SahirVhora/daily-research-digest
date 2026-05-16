import os
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from html import escape

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PRIORITY_KEYWORDS = [
    "benchmark", "launch", "release", "breakthrough", "beats", "outperforms",
    "state-of-the-art", "sota", "gpt", "claude", "gemini", "llama", "mistral",
    "qwen", "o3", "o4", "reasoning", "multimodal", "sap", "successfactors",
    "s/4hana", "btp", "open source", "weights released", "agentic", "mcp",
    "tool use", "nature", "peer-reviewed", "quantum"
]

AI_FEEDS = [
    ("OpenAI Blog", "https://openai.com/news/rss/"),
    ("Anthropic Blog", "https://www.anthropic.com/news/rss/"),
    ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml"),
    ("DeepMind Blog", "https://deepmind.google/blog/rss.xml"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
    ("Hacker News", "https://hnrss.org/frontpage?q=AI+OR+LLM+OR+machine+learning&points=100"),
]

SAP_FEEDS = [
    ("SAP News", "https://news.sap.com/feed/"),
    ("Google News SAP", "https://news.google.com/rss/search?q=SAP+SuccessFactors+OR+S%2F4HANA+OR+SAP+BTP&hl=en-GB&gl=GB&ceid=GB:en"),
]

ARXIV_FEEDS = [
    ("arXiv cs.AI", "https://rss.arxiv.org/rss/cs.AI"),
    ("arXiv cs.LG", "https://rss.arxiv.org/rss/cs.LG"),
    ("arXiv cs.CL", "https://rss.arxiv.org/rss/cs.CL"),
    ("arXiv cs.CV", "https://rss.arxiv.org/rss/cs.CV"),
]

SCIENCE_FEEDS = [
    ("Nature", "https://www.nature.com/nature.rss"),
    ("Science Daily AI", "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
]


def has_priority(text):
    t = text.lower()
    return any(kw in t for kw in PRIORITY_KEYWORDS)


def parse_feed(url, max_age_hours=48):
    try:
        feed = feedparser.parse(url)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        items = []
        for entry in feed.entries:
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                val = getattr(entry, attr, None)
                if val:
                    try:
                        published = datetime(*val[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass
                    break
            if published and published < cutoff:
                continue
            items.append(entry)
        return items
    except Exception:
        return []


def format_item(entry, source, star=False):
    title = escape(getattr(entry, "title", "No title").strip())
    link = getattr(entry, "link", "")
    star_str = " ⭐" if star else ""
    return f'• <a href="{link}">{title}</a>{star_str} <i>({source})</i>'


def get_summary(entry, max_chars=120):
    summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    # strip HTML tags simply
    import re
    summary = re.sub(r"<[^>]+>", "", summary).strip()
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return escape(summary)


def build_section(title, feed_list, max_per_source=3, max_age_hours=48):
    seen_urls = set()
    lines = [f"\n<b>{title}</b>\n"]
    for source, url in feed_list:
        items = parse_feed(url, max_age_hours)
        count = 0
        for entry in items:
            if count >= max_per_source:
                break
            link = getattr(entry, "link", "")
            if link in seen_urls:
                continue
            seen_urls.add(link)
            text = (getattr(entry, "title", "") + " " + getattr(entry, "summary", ""))
            star = has_priority(text)
            lines.append(format_item(entry, source, star))
            count += 1
    return "\n".join(lines)


def build_arxiv_section():
    seen_titles = set()
    all_papers = []
    for source, url in ARXIV_FEEDS:
        items = parse_feed(url, max_age_hours=24)
        count = 0
        for entry in items:
            if count >= 6:
                break
            title = getattr(entry, "title", "").strip()
            if title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            text = title + " " + getattr(entry, "summary", "")
            star = has_priority(text)
            all_papers.append((entry, source, star))
            count += 1

    # prioritise starred papers
    all_papers.sort(key=lambda x: (0 if x[2] else 1))

    lines = ["\n<b>🔬 Science &amp; Research</b>\n"]
    for source, url in SCIENCE_FEEDS:
        items = parse_feed(url, max_age_hours=48)
        count = 0
        seen_urls = set()
        for entry in items:
            if count >= 3:
                break
            link = getattr(entry, "link", "")
            if link in seen_urls:
                continue
            seen_urls.add(link)
            text = getattr(entry, "title", "") + " " + getattr(entry, "summary", "")
            star = has_priority(text)
            lines.append(format_item(entry, source, star))
            count += 1

    lines.append("\n<b>📄 arXiv Papers</b>")
    for entry, source, star in all_papers[:20]:
        title = escape(getattr(entry, "title", "").strip())
        link = getattr(entry, "link", "")
        summary = get_summary(entry)
        star_str = " ⭐" if star else ""
        lines.append(f'• <a href="{link}">{title}</a>{star_str} <i>({source})</i>')
        if summary:
            lines.append(f'  <i>{summary}</i>')

    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    last_response = None
    for part in split_message(text):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        last_response = resp.json()
    return last_response


def split_message(text, max_length=4000):
    if len(text) <= max_length:
        return [text]

    parts = []
    current = []
    current_len = 0

    for line in text.splitlines():
        addition = len(line) + (1 if current else 0)
        if current and current_len + addition > max_length:
            parts.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += addition

    if current:
        parts.append("\n".join(current))
    return parts


def main():
    now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
    header = f"<b>🗞 Daily Research Digest</b>\n<i>{now}</i>"

    ai_section = build_section("🤖 AI Tools &amp; Models", AI_FEEDS, max_per_source=3, max_age_hours=48)
    sap_section = build_section("🏢 SAP &amp; Enterprise", SAP_FEEDS, max_per_source=4, max_age_hours=48)
    science_section = build_arxiv_section()

    full_message = "\n".join([header, ai_section, sap_section, science_section])

    send_telegram(full_message)
    print("Digest sent successfully.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Gold & Silver Morning Alert
Fetches live prices from Yahoo Finance, calculates overnight move,
and sends a concise Telegram message.
Pure stdlib — no pip deps.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SYMBOLS = {
    "Gold":   "GC=F",
    "Silver": "SI=F",
}

YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch_price_data(symbol):
    """Fetch last 5 days of hourly data from Yahoo Finance."""
    query = urllib.parse.urlencode({"interval": "60m", "range": "5d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    req = urllib.request.Request(url, headers=YAHOO_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    meta = result["meta"]
    currency = meta.get("currency", "USD")
    return timestamps, closes, currency


def get_signal(pct):
    if pct >= 1.5:
        return "🚀 Strong rise"
    elif pct >= 0.5:
        return "📈 Rising"
    elif pct <= -1.5:
        return "🔻 Sharp drop"
    elif pct <= -0.5:
        return "📉 Falling"
    else:
        return "➡️ Flat"


def build_alert():
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%A %d %B %Y, %H:%M UTC")
    lines = [f"🥇 *Metals Morning Alert*\n_{date_str}_\n"]

    for metal, symbol in SYMBOLS.items():
        try:
            timestamps, closes, currency = fetch_price_data(symbol)

            # Get valid (non-None) closes with their timestamps
            pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
            if len(pairs) < 2:
                lines.append(f"*{metal}*: insufficient data\n")
                continue

            current_price = pairs[-1][1]

            # Previous close: last price from ~24h ago
            cutoff = pairs[-1][0] - 86400  # 24 hours back
            prev_pairs = [(t, c) for t, c in pairs if t <= cutoff]
            if not prev_pairs:
                prev_price = pairs[0][1]
            else:
                prev_price = prev_pairs[-1][1]

            change = current_price - prev_price
            pct = (change / prev_price) * 100
            signal = get_signal(pct)
            arrow = "+" if change >= 0 else ""

            # Week ago for context
            week_cutoff = pairs[-1][0] - 7 * 86400
            week_pairs = [(t, c) for t, c in pairs if t <= week_cutoff]
            week_line = ""
            if week_pairs:
                week_price = week_pairs[-1][1]
                week_pct = ((current_price - week_price) / week_price) * 100
                week_arrow = "+" if week_pct >= 0 else ""
                week_line = f"  7d: {week_arrow}{week_pct:.1f}%"

            lines.append(
                f"*{metal}* ({symbol})\n"
                f"  Price: {currency} {current_price:,.2f}\n"
                f"  24h:  {arrow}{change:+.2f} ({arrow}{pct:.2f}%)\n"
                f"  Signal: {signal}"
                + (f"\n{week_line}" if week_line else "")
            )
        except Exception as e:
            lines.append(f"*{metal}*: error fetching data — {e}")

        lines.append("")  # spacing

    # Simple tip based on moves
    return "\n".join(lines).strip()


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("No credentials — output:\n")
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
        print(f"Sent (message_id={result['result']['message_id']})")
    else:
        print(f"Telegram error: {result}")


if __name__ == "__main__":
    alert = build_alert()
    send_telegram(alert)

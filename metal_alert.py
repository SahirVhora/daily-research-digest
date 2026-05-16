#!/usr/bin/env python3
"""
Gold & Silver Morning Alert
Fetches live prices from Yahoo Finance, converts to GBP,
and sends a concise Telegram message.
Pure stdlib - no pip deps.

Gold  (GC=F): USD per troy oz  | 1g  = price / 31.1035
Silver(SI=F): USD per troy oz  | 1kg = price * 32.1507
FX    (GBPUSD=X): USD per 1 GBP
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TROY_OZ_PER_G  = 1 / 31.1035   # g  in 1 troy oz
TROY_OZ_PER_KG = 32.1507        # troy oz in 1 kg

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
    closes    = result["indicators"]["quote"][0]["close"]
    return timestamps, closes


def fetch_gbpusd():
    """Return current USD per GBP rate (e.g. 1.27 means £1 = $1.27)."""
    timestamps, closes = fetch_price_data("GBPUSD=X")
    pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
    if not pairs:
        raise ValueError("No GBPUSD data returned")
    return pairs[-1][1]


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
    now      = datetime.now(timezone.utc)
    date_str = now.strftime("%A %d %B %Y, %H:%M UTC")
    lines    = [f"🥇 *Metals Morning Alert*\n_{date_str}_\n"]

    # Fetch GBP/USD rate first
    try:
        gbpusd = fetch_gbpusd()
        fx_line = f"_FX: £1 = ${gbpusd:.4f}_"
    except Exception as e:
        gbpusd  = None
        fx_line = f"_FX: unavailable ({e})_"

    lines.append(fx_line + "\n")

    for metal, symbol in SYMBOLS.items():
        try:
            timestamps, closes = fetch_price_data(symbol)

            # Filter valid closes
            pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
            if len(pairs) < 2:
                lines.append(f"*{metal}*: insufficient data\n")
                continue

            usd_price = pairs[-1][1]

            # 24h change in USD
            cutoff     = pairs[-1][0] - 86400
            prev_pairs = [(t, c) for t, c in pairs if t <= cutoff]
            prev_usd   = prev_pairs[-1][1] if prev_pairs else pairs[0][1]
            change_usd = usd_price - prev_usd
            pct        = (change_usd / prev_usd) * 100
            signal     = get_signal(pct)
            arrow      = "+" if change_usd >= 0 else ""

            # 7-day context
            week_cutoff = pairs[-1][0] - 7 * 86400
            week_pairs  = [(t, c) for t, c in pairs if t <= week_cutoff]
            week_line   = ""
            if week_pairs:
                week_pct   = ((usd_price - week_pairs[-1][1]) / week_pairs[-1][1]) * 100
                week_arrow = "+" if week_pct >= 0 else ""
                week_line  = f"  7d: {week_arrow}{week_pct:.1f}%"

            # GBP conversion
            if gbpusd:
                gbp_price      = usd_price / gbpusd
                gbp_prev       = prev_usd / gbpusd
                change_gbp     = gbp_price - gbp_prev
                gbp_arrow      = "+" if change_gbp >= 0 else ""
                gbp_price_line = (
                    f"  GBP: £{gbp_price:,.2f}  "
                    f"({gbp_arrow}{change_gbp:+.2f})"
                )
            else:
                gbp_price_line = "  GBP: unavailable"
                gbp_price      = None

            # Per-unit prices
            if metal == "Gold":
                # 1 gram
                usd_per_g = usd_price * TROY_OZ_PER_G
                unit_usd  = f"${usd_per_g:.2f}/g"
                if gbp_price:
                    gbp_per_g = gbp_price * TROY_OZ_PER_G
                    unit_gbp  = f"£{gbp_per_g:.2f}/g"
                else:
                    unit_gbp  = ""
                unit_line = f"  1g: {unit_usd}  {unit_gbp}"
            else:
                # 1 kg silver
                usd_per_kg = usd_price * TROY_OZ_PER_KG
                unit_usd   = f"${usd_per_kg:,.2f}/kg"
                if gbp_price:
                    gbp_per_kg = gbp_price * TROY_OZ_PER_KG
                    unit_gbp   = f"£{gbp_per_kg:,.2f}/kg"
                else:
                    unit_gbp   = ""
                unit_line = f"  1kg: {unit_usd}  {unit_gbp}"

            lines.append(
                f"*{metal}* ({symbol})\n"
                f"  USD: ${usd_price:,.2f}  ({arrow}{change_usd:+.2f} | {arrow}{pct:.2f}%)\n"
                f"{gbp_price_line}\n"
                f"{unit_line}\n"
                f"  Signal: {signal}"
                + (f"\n{week_line}" if week_line else "")
            )
        except Exception as e:
            lines.append(f"*{metal}*: error fetching data - {e}")

        lines.append("")  # spacing

    return "\n".join(lines).strip()


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("No credentials - output:\n")
        print(text)
        return
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     text,
        "parse_mode":               "Markdown",
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

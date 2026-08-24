import logging
import os
import time
from datetime import datetime, timezone
from threading import Thread

import requests
from flask import Flask, jsonify

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = "XAU/USD"
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
ALERT_COOLDOWN_SECONDS = int(
    os.getenv("ALERT_COOLDOWN_SECONDS", "900")
)

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("gold-radar")

last_signal = None
last_alert_time = 0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_gold_quote():
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY is missing in Render."
        )

    response = requests.get(
        "https://api.twelvedata.com/quote",
        params={
            "symbol": SYMBOL,
            "apikey": TWELVE_DATA_API_KEY,
        },
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("status") == "error":
        raise RuntimeError(data.get("message", "Gold quote failed."))

    return {
        "price": float(data["close"]),
        "open": float(data.get("open", data["close"])),
        "high": float(data.get("high", data["close"])),
        "low": float(data.get("low", data["close"])),
        "change_percent": float(data.get("percent_change", 0)),
    }


def get_signal(quote):
    change = quote["change_percent"]

    if change >= 0.20:
        return "UP", "🟢", 0x22C55E

    if change <= -0.20:
        return "DOWN", "🔴", 0xEF4444

    return "WAIT", "🟡", 0xF59E0B


def post_discord(payload):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is missing in Render."
        )

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json=payload,
        timeout=20,
    )
    response.raise_for_status()


def build_embed(quote, signal_name, emoji, color):
    direction = {
        "UP": "Gold is moving upward from its daily open.",
        "DOWN": "Gold is moving downward from its daily open.",
        "WAIT": "Gold is near its daily open; no strong direction.",
    }[signal_name]

    return {
        "username": "Gold Radar",
        "embeds": [{
            "title": f"🥇 XAU/USD GOLD | {emoji} {signal_name}",
            "description": (
                f"**Live gold spot monitor**\n\n"
                f"**Signal:** {signal_name}\n"
                f"{direction}"
            ),
            "color": color,
            "fields": [
                {
                    "name": "💰 XAU/USD Price",
                    "value": f"**${quote['price']:,.2f}**",
                    "inline": True,
                },
                {
                    "name": "📊 Daily Change",
                    "value": (
                        f"**{quote['change_percent']:+.2f}%**"
                    ),
                    "inline": True,
                },
                {
                    "name": "📈 Daily Range",
                    "value": (
                        f"Low: **${quote['low']:,.2f}**\n"
                        f"High: **${quote['high']:,.2f}**"
                    ),
                    "inline": True,
                },
                {
                    "name": "⚠️ Safety",
                    "value": (
                        "Alert only, not financial advice. "
                        "Gold can move quickly around economic news, "
                        "central-bank decisions, and market-open periods."
                    ),
                    "inline": False,
                },
            ],
            "footer": {
                "text": "XAU/USD live quote • No automatic trading",
            },
            "timestamp": now_iso(),
        }],
    }


def send_startup_test():
    post_discord({
        "username": "Gold Radar",
        "embeds": [{
            "title": "✅ GOLD RADAR ONLINE",
            "description": (
                "XAU/USD live monitoring has started.\n"
                "Mode: Discord alerts only; no trades are placed."
            ),
            "color": 0x5865F2,
            "timestamp": now_iso(),
        }],
    })


def scan_gold():
    global last_signal
    global last_alert_time

    quote = get_gold_quote()
    signal_name, emoji, color = get_signal(quote)
    now = time.time()

    should_send = (
        signal_name != last_signal
        or now - last_alert_time >= ALERT_COOLDOWN_SECONDS
    )

    if should_send:
        post_discord(
            build_embed(
                quote,
                signal_name,
                emoji,
                color,
            )
        )

        last_signal = signal_name
        last_alert_time = now

        logger.info(
            "Gold alert sent: %s at $%s",
            signal_name,
            quote["price"],
        )
    else:
        logger.info(
            "No new gold alert: %s at $%s",
            signal_name,
            quote["price"],
        )


@app.get("/")
def home():
    return jsonify({
        "service": "Gold Radar",
        "symbol": SYMBOL,
        "status": "running",
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "time": now_iso(),
    })


def run_web_server():
    port = int(os.getenv("PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


def main():
    Thread(
        target=run_web_server,
        daemon=True,
    ).start()

    try:
        send_startup_test()
        logger.info("Gold Radar startup test sent.")
    except Exception:
        logger.exception("Gold Radar startup test failed.")

    while True:
        try:
            scan_gold()
        except Exception:
            logger.exception("Gold scan failed.")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

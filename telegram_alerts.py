"""Notify Telegram about new downward SMA crossings (optional).

Create repository Actions secrets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
No secrets are written to output files.
"""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram alerts disabled (no bot token/chat ID secrets).")
        return
    file = ROOT / "stockpilot_data" / "new_alerts.json"
    if not file.exists():
        print("No alert results found.")
        return
    alerts = json.loads(file.read_text(encoding="utf-8")).get("alerts", [])
    if not alerts:
        print("No new SMA crosses this scan. No notification sent.")
        return
    messages = ["StockPilot: new downward moving-average crosses"]
    for a in alerts:
        messages.append(
            f"{a['ticker']}: {a['event']} | price ${float(a['price']):,.2f} "
            f"| average ${float(a['moving_average']):,.2f} "
            f"| {a['price_mode']}"
        )
    message = "\n".join(messages)
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": message[:4000]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the alert (check secrets)")
    print(f"Sent {len(alerts)} new SMA crossover(s) to Telegram.")


if __name__ == "__main__":
    main()

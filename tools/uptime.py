"""Every 10 minutes: is https://api.atasakik.com/healthz up? (ScoutAI B2)

Three tries 20 s apart; healthy = HTTP 200 and "status": "ok". One Telegram
message when it goes down, one when it comes back (state in .uptime/state.json,
carried between runs by actions/cache). With TLS_CHECK=1, also warns when the
certificate expires within 21 days.
"""
import datetime as dt
import json
import os
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = os.environ.get("HEALTH_URL", "https://api.atasakik.com/healthz")
HOST = urllib.parse.urlparse(URL).hostname
STATE = Path(".uptime/state.json")
UA = {"User-Agent": "scoutai-uptime/1.0 (+https://github.com/AtaSakik/scoutai-ledger)"}


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("::warning::Telegram secrets not set — no alert sent")
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20)


def probe():
    last = "no answer"
    for attempt in range(3):
        try:
            req = urllib.request.Request(URL, headers=UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                body = json.loads(r.read() or b"{}")
                if r.status == 200 and body.get("status") == "ok":
                    return True, body
                last = f"HTTP {r.status} status={body.get('status')}"
        except Exception as e:                   # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < 2:
            time.sleep(20)
    return False, last


def tls_days_left():
    ctx = ssl.create_default_context()
    with socket.create_connection((HOST, 443), timeout=15) as sock, ctx.wrap_socket(sock, server_hostname=HOST) as s:
        not_after = s.getpeercert()["notAfter"]
    expiry = dt.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=dt.timezone.utc)
    return (expiry - dt.datetime.now(dt.timezone.utc)).days


def main() -> int:
    STATE.parent.mkdir(exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    up, detail = probe()
    if up:
        if state.get("down_since"):
            telegram(f"✅ ScoutAI API yeniden ayakta ({now}). Kesinti {state['down_since']} başlamıştı.")
        state = {"last_ok": now}
        crons = (detail or {}).get("crons_overdue")
        if crons:
            print(f"::warning::{crons} cron job(s) overdue")
    else:
        if not state.get("down_since"):
            telegram(f"🚨 ScoutAI API yanıt vermiyor ({now}): {detail}")
            state["down_since"] = now
        print(f"::error::down: {detail}")
    if os.environ.get("TLS_CHECK") == "1":
        days = tls_days_left()
        print(f"TLS certificate: {days} days left")
        if days < 21:
            telegram(f"⚠️ api.atasakik.com TLS sertifikasının bitmesine {days} gün var.")
    STATE.write_text(json.dumps(state))
    return 0 if up else 1


if __name__ == "__main__":
    sys.exit(main())

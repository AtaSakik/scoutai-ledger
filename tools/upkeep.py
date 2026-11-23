"""Daily: re-check yesterday's RFC 3161 tokens and upgrade OpenTimestamps proofs.

A fresh .ots file only holds calendar promises; `ots upgrade` replaces them with
the Bitcoin block path once the calendars have anchored (a few hours). Exit 1
(and a Telegram message, when configured) if any token no longer verifies.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20)


def main() -> int:
    bad, upgraded = [], 0
    for back in (1, 2, 3):
        day = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=back)).strftime("%Y/%m/%d")
        for f in sorted((ROOT / "ledger" / day).glob("*.json")):
            tsr = f.with_suffix(".json.tsr")
            if back == 1 and tsr.exists():
                ok = subprocess.run(["openssl", "ts", "-verify", "-in", str(tsr), "-data", str(f), "-CAfile",
                                     str(ROOT / "certs" / "cacert.pem"), "-untrusted",
                                     str(ROOT / "certs" / "tsa.crt")], capture_output=True).returncode == 0
                if not ok:
                    bad.append(str(f.relative_to(ROOT)))
            ots = f.with_suffix(".json.ots")
            if ots.exists():
                before = ots.read_bytes()
                subprocess.run(["ots", "upgrade", str(ots)], capture_output=True, timeout=120)
                upgraded += ots.read_bytes() != before
    print(json.dumps({"rfc3161_failed": bad, "ots_upgraded": upgraded}))
    if bad:
        telegram("ScoutAI ledger: RFC 3161 doğrulaması başarısız — " + ", ".join(bad[:5]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

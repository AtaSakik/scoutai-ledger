"""Daily: re-check yesterday's RFC 3161 tokens and upgrade OpenTimestamps proofs.

A fresh .ots file only holds calendar promises; `ots upgrade` replaces them with
the Bitcoin block path once the calendars have anchored (a few hours). Exit 1
(and a Telegram message, when configured) if any token no longer verifies.

Every hour file whose .ots is missing or proves other bytes is stamped again as
it is now; the new proof dates from this run, not from the hour.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# An .ots file opens with this magic, a version byte, the file-hash op
# (0x08 = SHA-256) and the 32-byte digest of the stamped file.
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"


def proof_matches(f: Path, ots: Path) -> bool:
    b = ots.read_bytes()
    start = len(OTS_MAGIC) + 2
    return (b.startswith(OTS_MAGIC) and len(b) >= start + 32 and b[len(OTS_MAGIC) + 1] == 0x08
            and b[start:start + 32] == hashlib.sha256(f.read_bytes()).digest())


def restamp_mismatched() -> list:
    """Stamp every hour file that has no proof, or a proof of earlier bytes.

    Until 2026-11-27 a second ledger run in the same hour rewrote HH.json but
    kept the first run's proof, because `ots stamp` will not overwrite one.
    """
    done = []
    for f in sorted((ROOT / "ledger").rglob("[0-9][0-9].json")):
        ots = f.with_suffix(".json.ots")
        if ots.exists() and proof_matches(f, ots):
            continue
        ots.unlink(missing_ok=True)
        try:
            subprocess.run(["ots", "stamp", str(f)], capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"::warning::OpenTimestamps stamp failed for {f.relative_to(ROOT)}: {e}")
            continue
        if ots.exists():
            done.append(str(f.relative_to(ROOT)))
    return done


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
    restamped = restamp_mismatched()
    print(json.dumps({"rfc3161_failed": bad, "ots_upgraded": upgraded, "ots_restamped": restamped}))
    if bad:
        telegram("ScoutAI ledger: RFC 3161 doğrulaması başarısız — " + ", ".join(bad[:5]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

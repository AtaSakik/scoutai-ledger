"""Hourly: store what the ScoutAI API commits to, and timestamp it independently.

Writes ledger/YYYY/MM/DD/HH.json = {"fetched_at": <this runner's UTC clock>,
"pending": <GET /predictions/ledger/pending>} when the set of commitments changed,
then attaches an RFC 3161 token from FreeTSA (HH.json.tsr) and an OpenTimestamps
proof (HH.json.ots). Failures of either timestamp do not stop the commit: the
GitHub history is a witness on its own.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("API", "https://api.atasakik.com")
UA = {"User-Agent": "scoutai-ledger/1.0 (+https://github.com/AtaSakik/scoutai-ledger)"}
ROOT = Path(__file__).resolve().parent.parent
TSA = "https://freetsa.org/tsr"


def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ensure_certs():
    for name in ("tsa.crt", "cacert.pem"):
        p = ROOT / "certs" / name
        if not p.exists():
            p.write_bytes(get(f"https://freetsa.org/files/{name}"))


def rfc3161(path: Path) -> bool:
    tsq, tsr = path.with_suffix(path.suffix + ".tsq"), path.with_suffix(path.suffix + ".tsr")
    try:
        subprocess.run(["openssl", "ts", "-query", "-data", str(path), "-no_nonce", "-sha256", "-cert",
                        "-out", str(tsq)], check=True, capture_output=True)
        req = urllib.request.Request(TSA, data=tsq.read_bytes(),
                                     headers={**UA, "Content-Type": "application/timestamp-query"})
        with urllib.request.urlopen(req, timeout=60) as r:
            tsr.write_bytes(r.read())
        subprocess.run(["openssl", "ts", "-verify", "-in", str(tsr), "-data", str(path), "-CAfile",
                        str(ROOT / "certs" / "cacert.pem"), "-untrusted", str(ROOT / "certs" / "tsa.crt")],
                       check=True, capture_output=True)
        return True
    except Exception as e:                       # noqa: BLE001
        print(f"::warning::RFC 3161 timestamp failed: {e}")
        tsr.unlink(missing_ok=True)
        return False
    finally:
        tsq.unlink(missing_ok=True)


def opentimestamps(path: Path) -> bool:
    ots = path.with_suffix(path.suffix + ".ots")
    # A second run in the same hour rewrites HH.json, and `ots stamp` refuses to
    # overwrite an existing proof: the proof of the earlier bytes stayed next to
    # the new file (four hours until 2026-11-27). Git history keeps that pair.
    ots.unlink(missing_ok=True)
    try:
        subprocess.run(["ots", "stamp", str(path)], check=True, capture_output=True, timeout=120)
        return ots.exists()
    except Exception as e:                       # noqa: BLE001
        print(f"::warning::OpenTimestamps stamp failed: {e}")
        return False


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    try:
        pending = json.loads(get(f"{API}/predictions/ledger/pending"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("::warning::/predictions/ledger/pending is not deployed yet")
            return 0
        raise
    state_path = ROOT / "ledger" / "latest.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if pending.get("root") == state.get("root"):
        print(f"unchanged ({pending.get('count')} commitments)")
        return 0
    ensure_certs()
    rel = f"ledger/{now:%Y/%m/%d/%H}.json"
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "pending": pending},
                               indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tsr, ots = rfc3161(path), opentimestamps(path)
    state_path.write_text(json.dumps({"root": pending.get("root"), "path": rel,
                                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, indent=1) + "\n")
    print(f"wrote {rel}: {pending.get('count')} commitments, rfc3161={tsr}, ots={ots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Check one ScoutAI prediction against this ledger.

    python tools/verify_prediction.py <match_id>

1. Fetches the revealed leaf from the API (only after kick-off).
2. Hashes it (compact JSON, sorted keys, UTF-8, SHA-256) — must equal leaf_hash.
3. Finds leaf_hash in the ledger file the API names, and checks that file was
   fetched before kick-off and that its RFC 3161 token verifies (openssl).
Nothing here trusts the API's word: the hash and the timestamps decide.
"""
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

API = "https://api.atasakik.com"
ROOT = Path(__file__).resolve().parent.parent


def main(match_id: str) -> int:
    proof = json.loads(urllib.request.urlopen(f"{API}/predictions/ledger/proof/{match_id}", timeout=30).read())
    if not proof.get("revealed"):
        print("not revealed yet: the match has not started")
        return 2
    leaf = proof["leaf"]
    digest = hashlib.sha256(json.dumps(leaf, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False).encode()).hexdigest()
    print(f"leaf hash      {digest}  {'OK' if digest == proof['leaf_hash'] else 'MISMATCH'}")
    witness = proof.get("witness")
    if not witness:
        print("no ledger file recorded for this match")
        return 1
    path = ROOT / witness["path"]
    doc = json.loads(path.read_text())
    found = any(c["leaf_hash"] == digest for c in doc["pending"]["commitments"])
    print(f"in {witness['path']}: {'yes' if found else 'NO'}; fetched {doc['fetched_at']}, kick-off {leaf['kickoff']}")
    tsr = path.with_suffix(".json.tsr")
    if tsr.exists():
        ok = subprocess.run(["openssl", "ts", "-verify", "-in", str(tsr), "-data", str(path), "-CAfile",
                             str(ROOT / "certs" / "cacert.pem"), "-untrusted", str(ROOT / "certs" / "tsa.crt")],
                            capture_output=True).returncode == 0
        print(f"RFC 3161 token {'verifies' if ok else 'DOES NOT verify'}")
    print(f"prediction     {leaf['outcome']} {leaf['score']}  H {leaf['p_home']} D {leaf['p_draw']} A {leaf['p_away']}")
    return 0 if digest == proof["leaf_hash"] and found and doc["fetched_at"] < leaf["kickoff"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

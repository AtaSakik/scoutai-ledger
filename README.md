# ScoutAI prediction ledger

Every football prediction the [ScoutAI](https://apps.apple.com/us/app/scoutai-ai-football-forecast/id6758396279)
app makes is committed here **before kick-off**, so anyone can check afterwards
that it was not changed or deleted. We do not ask you to trust our own logs.

## How it works

1. **Commit.** Every hour a GitHub Action in this repository fetches
   `https://api.atasakik.com/predictions/ledger/pending` — one SHA-256 hash per
   match kicking off in the next 48 hours — and stores it as
   `ledger/YYYY/MM/DD/HH.json`, with the runner's own clock in `fetched_at`.
   The predictions themselves stay hidden until kick-off.
2. **Timestamp.** Each file gets two timestamps we do not control: an
   [RFC 3161](https://www.rfc-editor.org/rfc/rfc3161) token from
   [FreeTSA](https://freetsa.org) (`HH.json.tsr`) and an
   [OpenTimestamps](https://opentimestamps.org) proof anchored in Bitcoin
   (`HH.json.ots`). The git history of this public repository is the third.
3. **Reveal.** Once the match has started,
   `https://api.atasakik.com/predictions/ledger/proof/<match_id>` returns the
   prediction ("leaf"): teams, kick-off, home/draw/away probabilities, the
   called outcome and score, and a random `nonce`. The nonce is why the hash
   could not be reversed before kick-off by trying every plausible prediction.
4. **Check.** `sha256(leaf)` (compact JSON, keys sorted, UTF-8) must equal the
   `leaf_hash` committed in a file fetched **before** kick-off.

The API refuses to change a prediction once its match has kicked off, so the
revealed leaf is the committed one.

**Season forecasts.** The first forecast of every league-season is sealed too:
its SHA-256 appears under `season_seals` in the hourly files for two weeks, and
`https://api.atasakik.com/championship/<league>/seal` publishes the content.
When the season ends, `/championship/<league>/report` grades it — misses included.

## Verify a prediction yourself

```bash
git clone https://github.com/AtaSakik/scoutai-ledger && cd scoutai-ledger
python3 tools/verify_prediction.py <match_id>          # hash, file, fetch time, RFC 3161
openssl ts -verify -in ledger/…/HH.json.tsr -data ledger/…/HH.json \
        -CAfile certs/cacert.pem -untrusted certs/tsa.crt
ots verify ledger/…/HH.json.ots                        # needs a Bitcoin node, or use opentimestamps.org
```

## Open data

`data/predictions.csv` — every resolved prediction, refreshed weekly, with the
`leaf_hash` and `nonce` that tie each row to this ledger (licence: CC BY 4.0).
Columns: `match_id, league_code, kickoff_utc, home, away, p_home, p_draw,
p_away, predicted_outcome, predicted_score, confidence, cold_start, home_score,
away_score, outcome, leaf_hash, nonce`. Probabilities are percentages.

```python
import csv, math
rows = list(csv.DictReader(open("data/predictions.csv")))
hit = sum(r["predicted_outcome"] == r["outcome"] for r in rows) / len(rows)
key = {"HOME": "p_home", "DRAW": "p_draw", "AWAY": "p_away"}
ll = sum(-math.log(max(1e-6, float(r[key[r["outcome"]]]) / 100)) for r in rows) / len(rows)
print(f"{len(rows)} predictions, hit rate {hit:.1%}, log-loss {ll:.3f}")
```

Not included: bookmaker odds, player data, crests, anything about users.

## Also here

`uptime` — a probe of the ScoutAI API every 10 minutes (alerts go to the operator).

ScoutAI is a football analysis app. It does not offer or promote betting.

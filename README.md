# predictions

Tools for the SIG Predictions Cup (Midterm Elections, Oct 1 – Nov 4, 2026) on the Super Market API.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste your API key (My Profile → API Keys)
```

## Pull markets
```bash
python pull_markets.py --list-tournaments
python pull_markets.py              # writes markets_flat.csv + markets_raw.json
python pull_markets.py --no-books   # prices only, much faster
```

## Layout
- `supermarket/client.py` – auth, 90 reads/min limiter, retries on 429/503 with Retry-After
- `supermarket/markets.py` – tournament lookup, flattening markets and order books
- `strategy/` – pricing logic (todo)

Planned: `orders.py` (idempotent placement/cancel), `realtime.py` (WebSocket feed + REST resync).

Notes: prices are YES-denominated (NO costs `1 − price`); orders target an `exchangeId`; always pass `tournamentId`.

#!/usr/bin/env python3
"""
Pull and flatten markets from the Super Market API (SIG Predictions Cup).

Setup:
    pip install requests
    export SUPERMARKET_API_KEY="your-key"      # My Profile -> API Keys (read scope is enough)

Usage:
    python pull_markets.py                      # auto-picks the "Midterm" tournament
    python pull_markets.py --list-tournaments   # see what your key can access
    python pull_markets.py --tournament-slug <slug>
    python pull_markets.py --no-books           # skip order books (much faster)

Outputs:
    markets_raw.json   raw /markets rows (+ order books) for exploration
    markets_flat.csv   one row per exchange (tradable outcome) with prices and top of book

Notes on the API (from the docs):
    * All prices are YES-denominated in [0, 1]. A NO share effectively costs 1 - price.
    * Every order targets an exchangeId, not a marketId.
    * Standard accounts get 100 reads/min shared across ALL your keys, so this
      script throttles itself (default 90/min) and honours Retry-After on 429/503.
    * Always pass tournamentId so you see the tournament's isolated book/prices,
      not some other context.
"""
import argparse
import csv
import json
import os
import sys

from dotenv import load_dotenv

from supermarket.client import DEFAULT_BASE, ApiError, SuperMarketClient
from supermarket.markets import as_list, flatten, pick_tournament

load_dotenv()

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.environ.get("SUPERMARKET_BASE", DEFAULT_BASE))
    ap.add_argument("--tournament-slug")
    ap.add_argument("--list-tournaments", action="store_true")
    ap.add_argument("--status", default="open", choices=["open", "closed", "settled", "any"])
    ap.add_argument("--no-books", action="store_true", help="skip per-market order book reads")
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--reads-per-min", type=int, default=90)
    ap.add_argument("--out", default="markets_flat.csv")
    args = ap.parse_args()

    key = os.environ.get("SUPERMARKET_API_KEY")
    if not key:
        raise SystemExit("Set SUPERMARKET_API_KEY first.")
    client = SuperMarketClient(key, args.base, args.reads_per_min)

    # 1. Verify key
    account = client.get("/account")
    print("Account OK:", json.dumps(account)[:300])

    # 2. Resolve tournament
    tournaments = as_list(client.get("/tournaments"))
    if args.list_tournaments:
        for t in tournaments:
            print(f"{t.get('slug'):30} {t.get('id')}  {t.get('name')}")
        return
    tourn = pick_tournament(tournaments, args.tournament_slug)
    tid = tourn["id"]
    print(f"Tournament: {tourn.get('name')} ({tourn.get('slug')}, {tid})")

    # 3. Markets in that tournament
    markets = list(client.paginate("/markets", {"tournamentId": tid, "status": args.status, "sort": "closing"}))
    print(f"Fetched {len(markets)} {args.status} markets")

    # 4. Order books (1 read per market; ~90/min)
    rows = []
    for i, m in enumerate(markets, 1):
        book = None
        if not args.no_books:
            try:
                book = client.get(f"/markets/{m['id']}/orderbook", {"tournamentId": tid, "depth": args.depth})
                m["_orderbook"] = book
            except ApiError as e:
                print(f"  book for market {m['id']} failed: {e}", file=sys.stderr)
            if i % 25 == 0:
                print(f"  books: {i}/{len(markets)}")
        rows.extend(flatten(m, tid, book))

    with open("markets_raw.json", "w") as f:
        json.dump({"tournament": tourn, "markets": markets}, f, indent=2)
    if rows:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {len(rows)} exchange rows to {args.out} and raw data to markets_raw.json")

    # 5. Quick look: widest overround / arb flags
    flagged = {r["market_id"]: r for r in rows if r["arb_flag"]}
    if flagged:
        print("\nMarkets the engine flags as arbitrage opportunities:")
        for r in flagged.values():
            print(f"  [{r['market_id']}] {r['market_title']}  overround={r['overround']}")


if __name__ == "__main__":
    main()

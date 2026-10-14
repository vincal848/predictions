"""Tournament discovery and market/orderbook flattening."""
def as_list(payload):
    if isinstance(payload, list):
        return payload
    for key in ("data", "tournaments", "items"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def pick_tournament(tournaments, slug=None, name_hint="midterm"):
    if slug:
        for t in tournaments:
            if t.get("slug") == slug:
                return t
        raise SystemExit(f"No accessible tournament with slug '{slug}'. Try --list-tournaments.")
    matches = [t for t in tournaments if name_hint in (t.get("name") or "").lower()]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(
        f"Found {len(matches)} tournaments matching '{name_hint}'. "
        "Run --list-tournaments and pass --tournament-slug."
    )


def context_for(market, tournament_id):
    for ctx in market.get("contexts") or []:
        if (ctx.get("tournament") or {}).get("id") == tournament_id:
            return ctx
    return (market.get("contexts") or [{}])[0]


def top_of_book(levels, best):
    if not levels:
        return None, None
    lvl = best(levels, key=lambda l: l["price"])
    return lvl["price"], lvl["quantity"]


def flatten(market, tournament_id, book=None):
    ctx = context_for(market, tournament_id)
    ctx_prices = {e["id"]: e.get("latestPrice") for e in ctx.get("exchanges") or []}
    books = {b["exchangeId"]: b for b in (book or {}).get("exchanges", [])}
    rows = []
    for ex in market.get("exchanges", []):
        b = books.get(ex["id"], {})
        bid, bid_qty = top_of_book(b.get("bids"), max)
        ask, ask_qty = top_of_book(b.get("asks"), min)
        mid = round((bid + ask) / 2, 4) if bid is not None and ask is not None else None
        rows.append({
            "market_id": market["id"],
            "market_title": market["title"],
            "status": ctx.get("status", market.get("status")),
            "settlement_date": market.get("settlementDate"),
            "categories": "; ".join(market.get("categories") or []),
            "is_multi_outcome": market.get("isMultiOutcome"),
            "exchange_id": ex["id"],
            "option": ex.get("option"),
            "last_price": ctx_prices.get(ex["id"]),   # null = no tournament trade yet
            "best_bid": bid, "bid_qty": bid_qty,
            "best_ask": ask, "ask_qty": ask_qty,
            "mid": mid,
            "spread": round(ask - bid, 4) if mid is not None else None,
            "implied_prob": b.get("impliedProbability"),
            "overround": (book or {}).get("overround"),
            "arb_flag": (book or {}).get("hasArbitrageOpportunity"),
            "book_sequence": (b.get("asOf") or {}).get("sequence"),
        })
    return rows

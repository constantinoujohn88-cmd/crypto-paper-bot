"""
Reconciles this project's paper-trade ledger against a real trade export
downloaded from Kraken - a sanity check for if/when you ever go live, to
confirm what actually executed on the exchange matches what the bot thinks
happened.

Not useful yet: while config.PAPER_MODE is True, nothing executes on
Kraken, so there's nothing real to reconcile against. Keep this ready for
if you ever wire up real trading (see README's "Going live" section) -
once you have, download your trade history from Kraken (Account ->
Export -> "Trades" - the exact menu wording can change, check Kraken's
current docs) and run this against it.

Kraken's trade export columns, as documented at the time of writing (check
your actual downloaded file - Kraken has changed this format before):
    txid, ordertxid, pair, time, type, ordertype, price, cost, fee, vol, margin, misc

A single order can fill in multiple pieces at different prices if the
order book didn't have enough depth at one level - Kraken gives one CSV
row per fill, all sharing the same ordertxid. This script groups fills by
ordertxid into one trade (summed volume/cost/fee, volume-weighted average
price, earliest fill time) before comparing against the bot's ledger,
which only ever records one row per buy/sell regardless of how it filled.

Matching is by nearest timestamp within --tolerance-minutes (default 5)
between a Kraken trade and a ledger trade of the same action (buy/sell) -
loose enough to survive the bot's own check interval, tight enough that
unrelated trades won't accidentally pair up.

Run with:
    python reconcile.py --bot 5m --kraken-export kraken_trades.csv
"""
import argparse
import csv
import json
import os
from datetime import datetime, timezone

import config

DEFAULT_TOLERANCE_MINUTES = 5


def _parse_kraken_time(value: str) -> datetime:
    """Kraken exports have used both unix timestamps and ISO strings for
    the 'time' column across different export tools - handle either."""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except ValueError:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_kraken_export(path: str) -> list[dict]:
    """Groups same-order fills into one trade per ordertxid."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    by_order = {}
    for row in rows:
        order_id = row.get("ordertxid") or row.get("txid")
        by_order.setdefault(order_id, []).append(row)

    trades = []
    for order_id, fills in by_order.items():
        fills.sort(key=lambda r: _parse_kraken_time(r["time"]))
        total_vol = sum(float(r["vol"]) for r in fills)
        total_cost = sum(float(r["cost"]) for r in fills)
        total_fee = sum(float(r["fee"]) for r in fills)
        avg_price = total_cost / total_vol if total_vol else 0.0
        trades.append({
            "order_id": order_id,
            "action": fills[0]["type"].lower(),  # Kraken: "buy" or "sell"
            "time": _parse_kraken_time(fills[0]["time"]),
            "price": avg_price,
            "vol": total_vol,
            "cost": total_cost,
            "fee": total_fee,
            "fill_count": len(fills),
        })
    return sorted(trades, key=lambda t: t["time"])


def load_ledger_trades(bot_key: str) -> list[dict]:
    path = config.bot_files(bot_key)["ledger"]
    if not os.path.exists(path):
        return []
    with open(path) as f:
        ledger = json.load(f)
    trades = []
    for t in ledger.get("trade_history", []):
        trades.append({
            "action": t["action"],
            "time": datetime.fromisoformat(t["timestamp"]),
            "price": t["price_gbp"],
            "vol": t["coin_amount"],
            "cost": t["cash_spent_gbp"] if t["action"] == "buy" else t["cash_received_gbp"],
            "fee": t.get("fee_gbp", 0.0),
        })
    return trades


def reconcile(kraken_trades: list[dict], ledger_trades: list[dict], tolerance_minutes: float) -> dict:
    tolerance = tolerance_minutes * 60
    unmatched_kraken = list(kraken_trades)
    unmatched_ledger = list(ledger_trades)
    matches = []

    for lt in list(ledger_trades):
        candidates = [
            kt for kt in unmatched_kraken
            if kt["action"] == lt["action"]
            and abs((kt["time"] - lt["time"]).total_seconds()) <= tolerance
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda kt: abs((kt["time"] - lt["time"]).total_seconds()))
        unmatched_kraken.remove(best)
        unmatched_ledger.remove(lt)
        matches.append({
            "action": lt["action"],
            "ledger_time": lt["time"], "kraken_time": best["time"],
            "price_diff_gbp": best["price"] - lt["price"],
            "vol_diff": best["vol"] - lt["vol"],
            "fee_diff_gbp": best["fee"] - lt["fee"],
            "kraken_fill_count": best.get("fill_count", 1),
        })

    return {"matches": matches, "unmatched_kraken": unmatched_kraken, "unmatched_ledger": unmatched_ledger}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", choices=list(config.BOTS.keys()), required=True)
    parser.add_argument("--kraken-export", required=True, help="Path to Kraken's trade history CSV")
    parser.add_argument("--tolerance-minutes", type=float, default=DEFAULT_TOLERANCE_MINUTES)
    args = parser.parse_args()

    kraken_trades = load_kraken_export(args.kraken_export)
    ledger_trades = load_ledger_trades(args.bot)

    print(f"Kraken export: {len(kraken_trades)} trade(s) (after grouping fills by order)")
    print(f"Bot ledger ({args.bot}): {len(ledger_trades)} trade(s)\n")

    if not ledger_trades:
        print(f"No trades in ledger_{args.bot}.json yet - nothing to reconcile.")
        return

    result = reconcile(kraken_trades, ledger_trades, args.tolerance_minutes)

    print(f"Matched: {len(result['matches'])}")
    for m in result["matches"]:
        flags = []
        if abs(m["price_diff_gbp"]) > 0.01:
            flags.append(f"price differs by £{m['price_diff_gbp']:+.2f}")
        if abs(m["vol_diff"]) > 1e-8:
            flags.append(f"volume differs by {m['vol_diff']:+.8f}")
        if abs(m["fee_diff_gbp"]) > 0.01:
            flags.append(f"fee differs by £{m['fee_diff_gbp']:+.2f}")
        note = " - " + "; ".join(flags) if flags else " - matches cleanly"
        fills_note = f" ({m['kraken_fill_count']} fill(s))" if m["kraken_fill_count"] > 1 else ""
        print(f"  {m['action']:>4} bot@{m['ledger_time']} <-> kraken@{m['kraken_time']}{fills_note}{note}")

    if result["unmatched_ledger"]:
        print(f"\nIn the bot's ledger but NOT found on Kraken ({len(result['unmatched_ledger'])}) - "
              "the bot thinks it traded but Kraken has no matching record:")
        for t in result["unmatched_ledger"]:
            print(f"  {t['action']:>4} at {t['time']}, price £{t['price']:.2f}, vol {t['vol']:.8f}")

    if result["unmatched_kraken"]:
        print(f"\nOn Kraken but NOT in the bot's ledger ({len(result['unmatched_kraken'])}) - "
              "Kraken executed something the bot doesn't have a record of:")
        for t in result["unmatched_kraken"]:
            print(f"  {t['action']:>4} at {t['time']}, price £{t['price']:.2f}, vol {t['vol']:.8f}")

    if not result["unmatched_ledger"] and not result["unmatched_kraken"]:
        print("\nEvery trade matched on both sides.")


if __name__ == "__main__":
    main()

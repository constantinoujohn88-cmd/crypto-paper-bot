"""
Exports a bot's trade history as a CSV with the fields a crypto tax tool
(or an accountant) typically wants: timestamp, action, amount, price, and
fee - plus the capital gain this project already computes per disposal,
since recomputing that from a raw exchange export is normally the hard
part of doing this by hand.

This is a convenience export of data already in ledger_<bot>.json, not a
tax return and not tax advice - see uk_tax.py and the README for exactly
what the gain figures do and don't account for.

Run with:
    python export_tax_csv.py --bot 5m    # one bot  -> tax_export_5m.csv
    python export_tax_csv.py --bot all   # all bots, combined and time-sorted -> tax_export.csv
"""
import argparse
import csv
import json
import os

import config

FIELDNAMES = [
    "bot", "timestamp", "tax_year", "action", "asset",
    "amount", "price_gbp", "gross_value_gbp", "fee_gbp",
    "net_value_gbp", "capital_gain_gbp",
]


def load_trades(bot_key: str) -> list[dict]:
    path = config.bot_files(bot_key)["ledger"]
    if not os.path.exists(path):
        return []
    with open(path) as f:
        ledger = json.load(f)
    return ledger.get("trade_history", [])


def to_row(bot_key: str, trade: dict) -> dict:
    amount = trade["coin_amount"]
    price = trade["price_gbp"]
    gross_value = amount * price
    fee = trade.get("fee_gbp", 0.0)
    # Buys and sells store their net cash flow under different keys (spend
    # vs proceeds) since one pays out and the other pays in - this picks
    # whichever applies rather than exposing that asymmetry in the export.
    net_value = trade["cash_spent_gbp"] if trade["action"] == "buy" else trade["cash_received_gbp"]
    return {
        "bot": bot_key,
        "timestamp": trade["timestamp"],
        "tax_year": trade.get("tax_year", ""),
        "action": trade["action"],
        "asset": config.KRAKEN_PAIR[:3],  # e.g. "XBT" from "XBTGBP"
        "amount": amount,
        "price_gbp": price,
        "gross_value_gbp": gross_value,
        "fee_gbp": fee,
        "net_value_gbp": net_value,
        "capital_gain_gbp": trade.get("capital_gain_gbp", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", choices=list(config.BOTS.keys()) + ["all"], default="all")
    args = parser.parse_args()

    bot_keys = list(config.BOTS.keys()) if args.bot == "all" else [args.bot]
    rows = []
    for bot_key in bot_keys:
        for trade in load_trades(bot_key):
            rows.append(to_row(bot_key, trade))

    rows.sort(key=lambda r: r["timestamp"])

    out_path = "tax_export.csv" if args.bot == "all" else f"tax_export_{args.bot}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} trade(s) to {out_path}")
    if not rows:
        print("No trades yet for the selected bot(s) - nothing to export.")


if __name__ == "__main__":
    main()

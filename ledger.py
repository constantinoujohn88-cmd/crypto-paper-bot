"""
Paper trading ledger. Tracks a simulated GBP balance and coin holdings,
persisted to a JSON file so state survives restarts. No real money or
real exchange account is touched by anything in this file.
"""
import json
import os
from datetime import datetime, timezone

import uk_tax


def load_ledger(path: str, starting_balance: float) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {
        "cash_gbp": starting_balance,
        "coin_holdings": 0.0,
        "fees_paid_gbp": 0.0,
        "cumulative_gross_proceeds_gbp": 0.0,
        "cumulative_net_gain_gbp": 0.0,
        "realized_gains_by_tax_year": {},
        "last_ma_relationship": None,
        "trade_history": [],
    }


def save_ledger(path: str, ledger: dict) -> None:
    with open(path, "w") as f:
        json.dump(ledger, f, indent=2)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_paper_buy(ledger: dict, price: float, fee_pct: float = 0.0) -> dict | None:
    """Spends all available cash on the coin at the given price, minus a
    trading fee (charged the way an exchange actually does it: taken out of
    what you receive, not added on top). Returns the trade record, or None
    if no cash."""
    if ledger["cash_gbp"] <= 0:
        return None

    spend = ledger["cash_gbp"]
    fee = spend * fee_pct
    coin_bought = (spend - fee) / price

    ledger["cash_gbp"] = 0.0
    ledger["coin_holdings"] += coin_bought
    ledger["fees_paid_gbp"] = ledger.get("fees_paid_gbp", 0.0) + fee

    trade = {
        "timestamp": _timestamp(),
        "action": "buy",
        "price_gbp": price,
        "coin_amount": coin_bought,
        "cash_spent_gbp": spend,
        "fee_gbp": fee,
        "cash_after": ledger["cash_gbp"],
        "coin_holdings_after": ledger["coin_holdings"],
    }
    ledger["trade_history"].append(trade)
    return trade


def execute_paper_sell(ledger: dict, price: float, fee_pct: float = 0.0) -> dict | None:
    """Sells all held coin at the given price, minus a trading fee taken out
    of the proceeds. Returns the trade record, or None if no holdings.

    Since a bot here is always either fully in cash or fully in coin (never
    a partial position, never buying again before selling what it holds),
    this sell always closes out exactly the preceding buy - so the UK
    capital gain for this round trip is just (net sale proceeds) minus
    (that buy's total cost, which already included its own fee). See
    uk_tax.py for what this is modelling and its simplifications."""
    if ledger["coin_holdings"] <= 0:
        return None

    coin_sold = ledger["coin_holdings"]
    gross_proceeds = coin_sold * price
    fee = gross_proceeds * fee_pct
    net_proceeds = gross_proceeds - fee

    ledger["coin_holdings"] = 0.0
    ledger["cash_gbp"] += net_proceeds
    ledger["fees_paid_gbp"] = ledger.get("fees_paid_gbp", 0.0) + fee

    timestamp = _timestamp()
    matching_buy = next(
        (t for t in reversed(ledger["trade_history"]) if t["action"] == "buy"), None
    )
    capital_gain = net_proceeds - matching_buy["cash_spent_gbp"] if matching_buy else None
    tax_year = uk_tax.uk_tax_year(timestamp)

    # Running totals so you can watch these accumulate trade-by-trade instead
    # of re-deriving them from trade_history later. "Gross proceeds" is the
    # sale value before the sell-side fee - the figure most tax tools/HMRC
    # worksheets want as the disposal value; "net gain" is the actual
    # profit/loss after both buy- and sell-side costs (same total you'd get
    # summing realized_gains_by_tax_year, just always at hand as one number).
    ledger["cumulative_gross_proceeds_gbp"] = ledger.get("cumulative_gross_proceeds_gbp", 0.0) + gross_proceeds
    if capital_gain is not None:
        ledger["cumulative_net_gain_gbp"] = ledger.get("cumulative_net_gain_gbp", 0.0) + capital_gain
        gains_by_year = ledger.setdefault("realized_gains_by_tax_year", {})
        gains_by_year[tax_year] = gains_by_year.get(tax_year, 0.0) + capital_gain

    trade = {
        "timestamp": timestamp,
        "action": "sell",
        "price_gbp": price,
        "coin_amount": coin_sold,
        "cash_received_gbp": net_proceeds,
        "fee_gbp": fee,
        "cash_after": ledger["cash_gbp"],
        "coin_holdings_after": ledger["coin_holdings"],
        "capital_gain_gbp": capital_gain,
        "tax_year": tax_year,
    }
    ledger["trade_history"].append(trade)
    return trade


def total_value_gbp(ledger: dict, current_price: float) -> float:
    return ledger["cash_gbp"] + ledger["coin_holdings"] * current_price

"""
Paper trading ledger. Tracks a simulated GBP balance and coin holdings,
persisted to a JSON file so state survives restarts. No real money or
real exchange account is touched by anything in this file.
"""
import json
import os
from datetime import datetime, timezone


def load_ledger(path: str, starting_balance: float) -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {
        "cash_gbp": starting_balance,
        "coin_holdings": 0.0,
        "fees_paid_gbp": 0.0,
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
    of the proceeds. Returns the trade record, or None if no holdings."""
    if ledger["coin_holdings"] <= 0:
        return None

    coin_sold = ledger["coin_holdings"]
    gross_proceeds = coin_sold * price
    fee = gross_proceeds * fee_pct
    net_proceeds = gross_proceeds - fee

    ledger["coin_holdings"] = 0.0
    ledger["cash_gbp"] += net_proceeds
    ledger["fees_paid_gbp"] = ledger.get("fees_paid_gbp", 0.0) + fee

    trade = {
        "timestamp": _timestamp(),
        "action": "sell",
        "price_gbp": price,
        "coin_amount": coin_sold,
        "cash_received_gbp": net_proceeds,
        "fee_gbp": fee,
        "cash_after": ledger["cash_gbp"],
        "coin_holdings_after": ledger["coin_holdings"],
    }
    ledger["trade_history"].append(trade)
    return trade


def total_value_gbp(ledger: dict, current_price: float) -> float:
    return ledger["cash_gbp"] + ledger["coin_holdings"] * current_price

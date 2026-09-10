"""
Entry point. Runs an infinite loop:
  1. Fetch recent price data
  2. Compute a buy/sell/hold signal
  3. Act on it (paper trade only, unless PAPER_MODE is turned off - see README)
  4. Log everything
  5. Sleep, repeat

Run with:  python main.py
Stop with: Ctrl+C
"""
import argparse
import csv
import logging
import os
import time
from datetime import datetime, timezone

import config
import data_fetcher
import ledger as ledger_module
import strategy


def append_history(path: str, row: dict) -> None:
    """Appends one price/portfolio snapshot per check, so the dashboard has
    continuous data to chart even on cycles with no trade."""
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if is_new:
            writer.writeheader()
        writer.writerow(row)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def place_live_order(action: str, price: float):
    """
    Placeholder for real order execution. Not implemented on purpose.

    Before wiring this up:
      - Read the "Going live" section of README.md
      - Store your Kraken API key/secret as environment variables, never in code
      - Implement Kraken's authenticated request signing (see their API docs)
      - Test with the smallest possible order size first
      - Add safeguards: max order size, daily loss limit, a kill switch
    """
    raise NotImplementedError(
        "Live trading is not implemented. This is intentional - see README.md "
        "'Going live' before writing this function."
    )


def run_once(ledger: dict) -> None:
    prices = data_fetcher.get_recent_closes(
        config.KRAKEN_PAIR, config.OHLC_INTERVAL_MINUTES
    )
    current_price = prices[-1]
    signal, short_ma, long_ma = strategy.compute_signal(
        prices, config.SHORT_MA_PERIOD, config.LONG_MA_PERIOD
    )

    logging.info(
        "Price: £%.2f | Signal: %s | Cash: £%.2f | Holdings: %.6f coin",
        current_price, signal, ledger["cash_gbp"], ledger["coin_holdings"],
    )

    trade = None
    if signal == "buy":
        if config.PAPER_MODE:
            trade = ledger_module.execute_paper_buy(ledger, current_price, config.TRADING_FEE_PCT)
        else:
            place_live_order("buy", current_price)
    elif signal == "sell":
        if config.PAPER_MODE:
            trade = ledger_module.execute_paper_sell(ledger, current_price, config.TRADING_FEE_PCT)
        else:
            place_live_order("sell", current_price)

    if trade:
        logging.info("Executed %s: %s", trade["action"].upper(), trade)
        ledger_module.save_ledger(config.LEDGER_FILE, ledger)

    total_value = ledger_module.total_value_gbp(ledger, current_price)
    logging.info("Portfolio value: £%.2f (started at £%.2f)",
                 total_value, config.STARTING_BALANCE_GBP)

    append_history(config.HISTORY_FILE, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_gbp": current_price,
        "short_ma": short_ma if short_ma is not None else "",
        "long_ma": long_ma if long_ma is not None else "",
        "signal": signal,
        "cash_gbp": ledger["cash_gbp"],
        "coin_holdings": ledger["coin_holdings"],
        "total_value_gbp": total_value,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single check and exit, instead of looping forever. "
             "Used when something else does the scheduling (e.g. GitHub Actions cron).",
    )
    args = parser.parse_args()

    setup_logging()

    if config.PAPER_MODE:
        logging.info("Running in PAPER MODE - no real money or real orders involved.")
    else:
        logging.warning("PAPER_MODE is False - this bot would attempt REAL orders.")

    ledger = ledger_module.load_ledger(config.LEDGER_FILE, config.STARTING_BALANCE_GBP)

    if args.once:
        run_once(ledger)
        return

    while True:
        try:
            run_once(ledger)
        except Exception as e:
            logging.error("Error during check: %s", e)

        time.sleep(config.CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

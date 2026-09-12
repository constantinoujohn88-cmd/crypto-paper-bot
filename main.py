"""
Entry point. Runs an infinite loop for ONE bot (see config.BOTS):
  1. Fetch recent price data at that bot's candle cadence
  2. Compute a buy/sell/hold signal
  3. Act on it (paper trade only, unless PAPER_MODE is turned off - see README)
  4. Log everything to that bot's own files
  5. Sleep, repeat

Multiple bots (different cadences, same strategy periods) run as completely
independent processes/invocations, each with --bot <key>, so their state
never mixes - that's what makes a fair side-by-side comparison possible.

Run with:  python main.py --bot 1h
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


def setup_logging(log_file: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,  # allow re-configuring if main() is invoked more than once in-process
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


def check_trailing_stop(ledger: dict, bot_cfg: dict, current_price: float) -> bool:
    """Returns True if a trailing-stop sell fired this check. See
    config.py's BOTS comment and backtest.py's run_backtest docstring for
    what this does and why it's only enabled where backtesting actually
    supported it. Independent of the crossover - this can sell even on a
    check where the strategy signal is "hold"."""
    trailing_stop_pct = bot_cfg.get("trailing_stop_pct")
    if ledger["coin_holdings"] <= 0 or trailing_stop_pct is None:
        return False

    peak = ledger.get("peak_since_buy")
    peak = current_price if peak is None else max(peak, current_price)
    ledger["peak_since_buy"] = peak

    arm_pct = bot_cfg.get("trailing_stop_arm_pct")
    buy_price = ledger.get("buy_price_for_position")
    armed = arm_pct is None or (
        buy_price is not None and peak >= buy_price * (1 + arm_pct / 100)
    )

    if not armed or current_price > peak * (1 - trailing_stop_pct / 100):
        return False

    if config.PAPER_MODE:
        trade = ledger_module.execute_paper_sell(ledger, current_price, config.TRADING_FEE_PCT)
        if trade:
            logging.info("Trailing stop triggered (peak £%.2f): %s", peak, trade)
    else:
        place_live_order("sell", current_price)
    ledger["peak_since_buy"] = None
    ledger["buy_price_for_position"] = None
    return True


def fee_aware_filtered(ledger: dict, bot_cfg: dict, price: float) -> bool:
    """Returns True if a buy/sell signal should be skipped because price
    hasn't moved far enough since the bot's last trade to plausibly clear
    paying the round-trip fee again - see config.py's BOTS comment and
    backtest.py's --fee-aware flag docstring for the reasoning and the
    evidence behind each bot's threshold. Disabled (returns False) if
    fee_aware_multiple isn't set, or there's no prior trade yet to compare
    against - the very first trade is never filtered."""
    multiple = bot_cfg.get("fee_aware_multiple")
    last_trade_price = ledger.get("last_trade_price")
    if multiple is None or last_trade_price is None:
        return False
    round_trip_fee_pct = config.TRADING_FEE_PCT * 2 * 100
    move_pct = abs(price - last_trade_price) / last_trade_price * 100
    return move_pct < round_trip_fee_pct * multiple


def run_once(ledger: dict, bot_cfg: dict, files: dict) -> None:
    prices = data_fetcher.get_recent_closes(
        config.KRAKEN_PAIR, bot_cfg["interval_minutes"]
    )
    current_price = prices[-1]
    short_ma, long_ma = strategy.moving_averages(
        prices, bot_cfg["short_period"], bot_cfg["long_period"]
    )
    signal, current_relationship = strategy.compute_signal(
        short_ma, long_ma, ledger.get("last_ma_relationship")
    )
    ledger["last_ma_relationship"] = current_relationship

    logged_signal = signal
    trade = None

    if check_trailing_stop(ledger, bot_cfg, current_price):
        logged_signal = "sell"  # so the dashboard's chart marker/coloring shows this exit
    else:
        logging.info(
            "Price: £%.2f | Signal: %s | Cash: £%.2f | Holdings: %.6f coin",
            current_price, signal, ledger["cash_gbp"], ledger["coin_holdings"],
        )

        if signal in ("buy", "sell") and fee_aware_filtered(ledger, bot_cfg, current_price):
            logged_signal = "hold"  # filtered - not retried, same as backtest.py's --fee-aware
            logging.info(
                "%s signal filtered (fee-aware): price only moved %.3f%% since last "
                "trade at £%.2f, needs %.3f%%",
                signal.upper(), abs(current_price - ledger["last_trade_price"]) / ledger["last_trade_price"] * 100,
                ledger["last_trade_price"], config.TRADING_FEE_PCT * 2 * 100 * bot_cfg["fee_aware_multiple"],
            )
        elif signal == "buy":
            if config.PAPER_MODE:
                trade = ledger_module.execute_paper_buy(ledger, current_price, config.TRADING_FEE_PCT)
                if ledger["coin_holdings"] > 0:
                    ledger["peak_since_buy"] = current_price
                    ledger["buy_price_for_position"] = current_price
                    ledger["last_trade_price"] = current_price
            else:
                place_live_order("buy", current_price)
        elif signal == "sell":
            if config.PAPER_MODE:
                trade = ledger_module.execute_paper_sell(ledger, current_price, config.TRADING_FEE_PCT)
                if trade:
                    ledger["last_trade_price"] = current_price
            else:
                place_live_order("sell", current_price)
            ledger["peak_since_buy"] = None
            ledger["buy_price_for_position"] = None

        if trade:
            logging.info("Executed %s: %s", trade["action"].upper(), trade)

    # Always persist, not just on a trade - last_ma_relationship (and the
    # trailing-stop/fee-aware tracking fields) have to survive to the next
    # run to work at all.
    ledger_module.save_ledger(files["ledger"], ledger)

    total_value = ledger_module.total_value_gbp(ledger, current_price)
    logging.info("Portfolio value: £%.2f (started at £%.2f)",
                 total_value, config.STARTING_BALANCE_GBP)

    append_history(files["history"], {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "price_gbp": current_price,
        "short_ma": short_ma if short_ma is not None else "",
        "long_ma": long_ma if long_ma is not None else "",
        "signal": logged_signal,
        "cash_gbp": ledger["cash_gbp"],
        "coin_holdings": ledger["coin_holdings"],
        "total_value_gbp": total_value,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bot", choices=list(config.BOTS.keys()), default=config.DEFAULT_BOT,
        help="Which bot config to run (see config.BOTS) - each has its own "
             "candle cadence and its own ledger/history/log files.",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single check and exit, instead of looping forever. "
             "Used when something else does the scheduling (e.g. railway_worker.py).",
    )
    args = parser.parse_args()

    bot_cfg = config.BOTS[args.bot]
    files = config.bot_files(args.bot)

    setup_logging(files["log"])

    if config.PAPER_MODE:
        logging.info("[%s] Running in PAPER MODE - no real money or real orders involved.", args.bot)
    else:
        logging.warning("[%s] PAPER_MODE is False - this bot would attempt REAL orders.", args.bot)

    ledger = ledger_module.load_ledger(files["ledger"], config.STARTING_BALANCE_GBP)

    if args.once:
        run_once(ledger, bot_cfg, files)
        return

    while True:
        try:
            run_once(ledger, bot_cfg, files)
        except Exception as e:
            logging.error("Error during check: %s", e)

        time.sleep(config.CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

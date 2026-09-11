"""
Backtests the moving-average crossover strategy against real historical
prices, using the exact same signal and fee logic as the live bot
(strategy.py, ledger.py) - so results reflect what the bot would actually
have done, not a separate reimplementation that could quietly drift out of
sync.

Two price sources:
  --source kraken   Fetch Kraken's public OHLC data (default). A request is
                     always capped at ~720 candles regardless of candle
                     size, so --interval (or --bot's own cadence) trades off
                     look-back length against signal granularity: 5-min
                     candles get ~2.5 days of history, hourly gets ~30 days,
                     daily gets ~2 years.
  --source history  Use one bot's own history_<bot>.csv, built up by its
                     live scheduled checks. Short at first, but grows every
                     time that bot runs - the longer it's been live, the
                     more meaningful a backtest against its own real data
                     becomes.

Doesn't touch any bot's ledger or live state. Read-only.

Run with: python backtest.py [--bot 5m|1h|1d] [--source kraken|history] [--interval N]
"""
import argparse
import csv

import config
import data_fetcher
import ledger as ledger_module
import strategy

# A handful of sane period pairs to compare, not an exhaustive sweep -
# scanning hundreds of combinations against ~2.5 days of data would just
# overfit to noise, not find a genuinely better strategy.
PARAM_SETS = [
    (6, 13),
    (12, 26),   # current default (config.py)
    (12, 50),
    (20, 50),
]


def load_kraken_prices(pair: str, interval_minutes: int) -> list[float]:
    return data_fetcher.get_recent_closes(pair, interval_minutes, count=720)


def load_history_csv_prices(path: str) -> list[float]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return [float(r["price_gbp"]) for r in rows if r.get("price_gbp")]


def run_backtest(prices: list[float], short_period: int, long_period: int,
                  fee_pct: float, starting_balance: float, common_start: int) -> dict:
    """common_start is a shared warm-up index (the same for every parameter
    set being compared) so the buy & hold benchmark is measured over
    identical price windows across rows - each strategy still only starts
    trading once IT has enough history, but the comparison baseline doesn't
    silently shift with the period lengths being tested."""
    ledger = {
        "cash_gbp": starting_balance,
        "coin_holdings": 0.0,
        "fees_paid_gbp": 0.0,
        "trade_history": [],
    }
    equity_curve = []
    prev_relationship = None

    for i in range(long_period, len(prices) + 1):
        window = prices[:i]
        price = window[-1]
        short_ma, long_ma = strategy.moving_averages(window, short_period, long_period)
        signal, prev_relationship = strategy.compute_signal(short_ma, long_ma, prev_relationship)

        if signal == "buy":
            ledger_module.execute_paper_buy(ledger, price, fee_pct)
        elif signal == "sell":
            ledger_module.execute_paper_sell(ledger, price, fee_pct)

        equity_curve.append(ledger["cash_gbp"] + ledger["coin_holdings"] * price)

    if not equity_curve:
        return None

    final_value = equity_curve[-1]
    peak = starting_balance
    max_drawdown_pct = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        max_drawdown_pct = max(max_drawdown_pct, (peak - v) / peak * 100)

    buy_hold_return_pct = (prices[-1] / prices[common_start] - 1) * 100

    return {
        "short_period": short_period,
        "long_period": long_period,
        "trades": len(ledger["trade_history"]),
        "return_pct": (final_value / starting_balance - 1) * 100,
        "fees_paid_gbp": ledger["fees_paid_gbp"],
        "max_drawdown_pct": max_drawdown_pct,
        "buy_hold_return_pct": buy_hold_return_pct,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["kraken", "history"], default="kraken")
    parser.add_argument("--bot", choices=list(config.BOTS.keys()), default=config.DEFAULT_BOT,
                         help="Which bot's cadence to default to, and (with "
                              "--source history) whose history_<bot>.csv to load.")
    parser.add_argument("--interval", type=int, default=None,
                         help="Candle size in minutes (Kraken accepts 1, 5, 15, 30, 60, "
                              "240, 1440, 10080, 21600), overriding --bot's own interval. "
                              "Kraken always caps a request at ~720 candles, so a bigger "
                              "interval buys a longer look-back at the cost of coarser signals.")
    args = parser.parse_args()

    bot_cfg = config.BOTS[args.bot]
    interval = args.interval if args.interval is not None else bot_cfg["interval_minutes"]

    if args.source == "kraken":
        print(f"Fetching Kraken's available {config.KRAKEN_PAIR} "
              f"{interval}-min candle history (capped at ~720 candles by "
              "Kraken's public API)...")
        prices = load_kraken_prices(config.KRAKEN_PAIR, interval)
    else:
        history_file = config.bot_files(args.bot)["history"]
        print(f"Loading price history from {history_file}...")
        prices = load_history_csv_prices(history_file)

    hours = len(prices) * interval / 60
    span = f"{hours/24:.1f} days" if hours >= 48 else f"{hours:.1f} hours"
    print(f"Got {len(prices)} candles (~{span} of data, {interval}-min each)\n")

    max_period = max(long_p for _, long_p in PARAM_SETS)
    if len(prices) < max_period + 2:
        print(f"Not enough data yet - need at least {max_period + 2} candles, "
              f"have {len(prices)}. Try again once more history has built up.")
        return

    common_start = max_period  # same warm-up point for every row's buy & hold comparison

    def real_time(period):
        h = period * interval / 60
        return f"{h/24:.1f}d" if h >= 48 else f"{h:.1f}h"

    print(f"{'Short':>6} {'Long':>6} {'(real time)':>18} {'Trades':>7} {'Return %':>9} "
          f"{'Fees £':>8} {'Max DD %':>9} {'Buy&Hold %':>11}")
    for short_p, long_p in PARAM_SETS:
        result = run_backtest(prices, short_p, long_p, config.TRADING_FEE_PCT,
                               config.STARTING_BALANCE_GBP, common_start)
        if result is None:
            continue
        marker = " <- this bot's config" if (short_p, long_p) == (bot_cfg["short_period"], bot_cfg["long_period"]) and interval == bot_cfg["interval_minutes"] else ""
        real = f"({real_time(short_p)}/{real_time(long_p)})"
        print(f"{result['short_period']:>6} {result['long_period']:>6} {real:>18} "
              f"{result['trades']:>7} {result['return_pct']:>9.2f} "
              f"{result['fees_paid_gbp']:>8.2f} {result['max_drawdown_pct']:>9.2f} "
              f"{result['buy_hold_return_pct']:>11.2f}{marker}")

    print("\nBuy&Hold % is the same for every row (same price window) - it's "
          "there as a sanity check, not something to beat with limited data. "
          "Treat all of this as directional, not conclusive: it's a short "
          "window, and past prices don't predict future ones.")


if __name__ == "__main__":
    main()

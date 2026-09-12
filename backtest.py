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
                  fee_pct: float, starting_balance: float, common_start: int,
                  max_extension_pct: float | None = None,
                  trailing_stop_pct: float | None = None,
                  trailing_stop_arm_pct: float | None = None,
                  fee_aware_multiple: float | None = None,
                  breakout_lookback: int | None = None) -> dict:
    """common_start is a shared warm-up index (the same for every parameter
    set being compared) so the buy & hold benchmark is measured over
    identical price windows across rows - each strategy still only starts
    trading once IT has enough history, but the comparison baseline doesn't
    silently shift with the period lengths being tested.

    max_extension_pct is an EXPERIMENTAL filter, not used by the live bots:
    when set, a buy/sell is skipped if the current price is already more
    than this %% away from the short MA at that moment - the idea being to
    avoid chasing a move that's already run far from its own recent average
    by the time a delayed check notices the crossover (see the real
    examples of this in the project's history). A skipped signal isn't
    retried later - the relationship tracking moves on regardless, so this
    specific crossover is simply forgone, for better or worse.

    trailing_stop_pct is also EXPERIMENTAL and backtest-only: while holding
    coin, tracks the highest price seen since the buy, and sells immediately
    (independent of the crossover) if price falls back this %% from that
    peak. The idea is to lock in a gain on the way down from a top rather
    than waiting for the slower long-MA-based sell to confirm a reversal -
    the risk is exiting a dip that was about to resume into a bigger move.

    trailing_stop_arm_pct (also experimental) makes the trailing stop wait
    until it has something worth protecting: it only starts watching for a
    pullback once price has risen at least this %% above the BUY price
    (not the peak). Before that, only the crossover sell can exit - a bad
    entry (e.g. bought right at a local spike) gets room to recover instead
    of being stopped out for a small loss the moment it wobbles. Ignored if
    trailing_stop_pct isn't also set.

    fee_aware_multiple is also EXPERIMENTAL and backtest-only: skips a
    buy/sell if price hasn't moved at least this multiple of the
    round-trip fee cost (fee_pct paid twice - once in, once out) since the
    LAST TRADE (not the last check). The idea: every round trip pays the
    fee twice regardless of outcome, so a new trade that reverses the last
    one at close to the same price is close to guaranteed to lose to fees
    - this skips exactly that case, the classic whipsaw in a choppy,
    sideways market. (An earlier version of this compared the %% gap
    between the two MAs at the moment of crossover instead - that's a
    dead end: a crossover is BY DEFINITION the point where the two
    averages are equal, so that gap is always ~0 right when a signal
    fires, and the filter ended up rejecting essentially every trade
    regardless of the threshold. Confirmed by testing it against real
    data before landing on this version.) A multiple of 1.0 requires the
    move to at least match the round-trip fee cost; 2.0 requires double
    that, etc. The very first trade is never filtered, since there's no
    prior trade price to compare against. Like the other filters, a
    skipped signal is simply forgone, not retried.

    breakout_lookback is also EXPERIMENTAL and backtest-only: a HYBRID
    entry, not a filter - while in cash, buys immediately (independent of
    the crossover) the moment price closes above the highest price of the
    preceding breakout_lookback candles, instead of waiting for the short
    MA to catch up and cross the long MA. The idea is to catch the start
    of a fast move that a lagging crossover would otherwise miss entirely
    (the crossover buy still exists as a fallback for slower-building
    trends that never produce a sharp breakout). The other filters
    (max_extension_pct, fee_aware_multiple) still apply to a
    breakout-triggered buy exactly as they would to a crossover one - a
    breakout right on the heels of the last trade at a similar price is
    still a fee-losing whipsaw and still gets skipped. Selling is
    unchanged - still crossover (and trailing stop, if enabled)."""
    ledger = {
        "cash_gbp": starting_balance,
        "coin_holdings": 0.0,
        "fees_paid_gbp": 0.0,
        "trade_history": [],
    }
    equity_curve = []
    prev_relationship = None
    filtered_count = 0
    trailing_stop_count = 0
    peak_since_buy = None
    buy_price = None
    last_trade_price = None  # price of the most recent trade (buy, sell, or trailing-stop sell)
    round_trip_fee_pct = fee_pct * 2 * 100
    breakout_count = 0

    for i in range(long_period, len(prices) + 1):
        window = prices[:i]
        price = window[-1]
        short_ma, long_ma = strategy.moving_averages(window, short_period, long_period)
        signal, prev_relationship = strategy.compute_signal(short_ma, long_ma, prev_relationship)

        triggered_by_breakout = False
        if (signal == "hold" and ledger["coin_holdings"] <= 0
                and breakout_lookback is not None and i - 1 >= breakout_lookback):
            lookback_window = prices[i - 1 - breakout_lookback:i - 1]
            if lookback_window and price > max(lookback_window):
                signal = "buy"
                triggered_by_breakout = True

        if ledger["coin_holdings"] > 0 and trailing_stop_pct is not None:
            peak_since_buy = price if peak_since_buy is None else max(peak_since_buy, price)
            armed = (
                trailing_stop_arm_pct is None
                or peak_since_buy >= buy_price * (1 + trailing_stop_arm_pct / 100)
            )
            if armed and price <= peak_since_buy * (1 - trailing_stop_pct / 100):
                ledger_module.execute_paper_sell(ledger, price, fee_pct)
                trailing_stop_count += 1
                peak_since_buy = None
                buy_price = None
                last_trade_price = price
                equity_curve.append(ledger["cash_gbp"] + ledger["coin_holdings"] * price)
                continue

        filtered = False
        if signal in ("buy", "sell") and max_extension_pct is not None and short_ma:
            extension_pct = abs(price - short_ma) / short_ma * 100
            filtered = extension_pct > max_extension_pct

        if signal in ("buy", "sell") and fee_aware_multiple is not None and last_trade_price is not None:
            move_pct = abs(price - last_trade_price) / last_trade_price * 100
            filtered = filtered or (move_pct < round_trip_fee_pct * fee_aware_multiple)

        if filtered:
            filtered_count += 1
        elif signal == "buy":
            ledger_module.execute_paper_buy(ledger, price, fee_pct)
            if ledger["coin_holdings"] > 0:
                peak_since_buy = price
                buy_price = price
                last_trade_price = price
                if triggered_by_breakout:
                    breakout_count += 1
        elif signal == "sell":
            ledger_module.execute_paper_sell(ledger, price, fee_pct)
            peak_since_buy = None
            buy_price = None
            last_trade_price = price

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
        "filtered_count": filtered_count,
        "trailing_stop_count": trailing_stop_count,
        "breakout_count": breakout_count,
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
    parser.add_argument("--max-extension", type=float, default=None,
                         help="EXPERIMENTAL, backtest-only (not used by the live bots): "
                              "skip a buy/sell if price is more than this %% away from the "
                              "short MA at that moment. Prints both filtered and unfiltered "
                              "results side by side for comparison when set.")
    parser.add_argument("--trailing-stop", type=float, default=None,
                         help="EXPERIMENTAL, backtest-only (not used by the live bots unless "
                              "set in config.BOTS): while holding, sell immediately "
                              "(independent of the crossover) if price falls back this %% "
                              "from its peak since the buy, instead of waiting for the sell "
                              "signal. Prints with and without for comparison when set.")
    parser.add_argument("--trailing-stop-arm", type=float, default=None,
                         help="Only meaningful with --trailing-stop: don't start watching "
                              "for a pullback until price has first risen at least this %% "
                              "above the buy price, so a bad entry gets room to recover "
                              "instead of being stopped out immediately.")
    parser.add_argument("--fee-aware", type=float, default=None,
                         help="EXPERIMENTAL, backtest-only (not used by the live bots): "
                              "skip a buy/sell if price hasn't moved at least this multiple "
                              "of the round-trip fee cost since the last trade - i.e. skip "
                              "trades unlikely to clear paying the fee twice. 1.0 = move must "
                              "at least match the round-trip fee %%, 2.0 = double that, etc. "
                              "Prints with and without for comparison when set.")
    parser.add_argument("--breakout", type=int, default=None,
                         help="EXPERIMENTAL, backtest-only (not used by the live bots): a "
                              "HYBRID entry - while in cash, buy immediately the moment price "
                              "closes above the highest price of the preceding N candles, "
                              "instead of waiting for the crossover. Meant to catch a fast "
                              "move a lagging crossover would otherwise miss. --max-extension "
                              "and --fee-aware still apply to a breakout-triggered buy. Prints "
                              "with and without for comparison when set.")
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

    def print_row(result, label, marker=""):
        real = f"({real_time(result['short_period'])}/{real_time(result['long_period'])})"
        notes = []
        if result["filtered_count"]:
            notes.append(f"{result['filtered_count']} filtered")
        if result["trailing_stop_count"]:
            notes.append(f"{result['trailing_stop_count']} trailing-stopped")
        if result["breakout_count"]:
            notes.append(f"{result['breakout_count']} breakout-bought")
        note_str = f" [{', '.join(notes)}]" if notes else ""
        print(f"{label:>16} {result['short_period']:>6} {result['long_period']:>6} {real:>18} "
              f"{result['trades']:>7} {result['return_pct']:>9.2f} "
              f"{result['fees_paid_gbp']:>8.2f} {result['max_drawdown_pct']:>9.2f} "
              f"{result['buy_hold_return_pct']:>11.2f}{marker}{note_str}")

    variants = [("baseline", {})]
    if args.max_extension is not None:
        variants.append((f"ext<{args.max_extension:g}%", {"max_extension_pct": args.max_extension}))
    if args.trailing_stop is not None:
        trail_kwargs = {"trailing_stop_pct": args.trailing_stop}
        trail_label = f"trail{args.trailing_stop:g}%"
        if args.trailing_stop_arm is not None:
            trail_kwargs["trailing_stop_arm_pct"] = args.trailing_stop_arm
            trail_label += f"/arm{args.trailing_stop_arm:g}%"
        variants.append((trail_label, trail_kwargs))
    if args.max_extension is not None and args.trailing_stop is not None:
        variants.append(("both", {**trail_kwargs, "max_extension_pct": args.max_extension}))
    if args.fee_aware is not None:
        variants.append((f"fee-aware{args.fee_aware:g}x", {"fee_aware_multiple": args.fee_aware}))
    if args.breakout is not None:
        variants.append((f"breakout{args.breakout}", {"breakout_lookback": args.breakout}))
    if args.breakout is not None and args.fee_aware is not None:
        variants.append(("breakout+fee-aware", {"breakout_lookback": args.breakout,
                                                  "fee_aware_multiple": args.fee_aware}))

    header_label = "Variant" if len(variants) > 1 else ""
    print(f"{header_label:>16} {'Short':>6} {'Long':>6} {'(real time)':>18} {'Trades':>7} {'Return %':>9} "
          f"{'Fees £':>8} {'Max DD %':>9} {'Buy&Hold %':>11}")
    for short_p, long_p in PARAM_SETS:
        marker = " <- this bot's config" if (short_p, long_p) == (bot_cfg["short_period"], bot_cfg["long_period"]) and interval == bot_cfg["interval_minutes"] else ""
        for label, kwargs in variants:
            result = run_backtest(prices, short_p, long_p, config.TRADING_FEE_PCT,
                                   config.STARTING_BALANCE_GBP, common_start, **kwargs)
            if result is None:
                continue
            print_row(result, label if len(variants) > 1 else "", marker)

    print("\nBuy&Hold % is the same for every row (same price window) - it's "
          "there as a sanity check, not something to beat with limited data. "
          "Treat all of this as directional, not conclusive: it's a short "
          "window, and past prices don't predict future ones.")
    if len(variants) > 1:
        print("\n--max-extension and --breakout are experimental and backtest-only - not used "
              "by any live bot. --trailing-stop and --fee-aware ARE used live for bots that "
              "have trailing_stop_pct/fee_aware_multiple set in config.BOTS (currently: 1h for "
              "trailing-stop; 5m and 1h for fee-aware) - check there for what's actually "
              "deployed, these flags only let you test other values here first. A trade shown "
              "as filtered was skipped entirely (not retried, by either filter); a "
              "trailing-stopped sell fired early, independent of the crossover signal; a "
              "breakout-bought trade bought early, independent of the crossover signal.")


if __name__ == "__main__":
    main()

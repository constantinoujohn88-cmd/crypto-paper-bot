"""
Central config. Change these values to tune the bot.
"""

# --- Market ---
KRAKEN_PAIR = "XBTGBP"          # BTC/GBP on Kraken. See https://api.kraken.com/0/public/AssetPairs

# --- Multiple bots, same strategy, different candle cadence ---
# Each runs completely independently (its own £100, own ledger, own history)
# so you can directly compare how much cadence alone changes the outcome.
# Short/long periods are deliberately IDENTICAL across bots - cadence is the
# only variable being tested, not the strategy tuning. See backtest.py for
# evidence this matters: which period pair "wins" flips depending on the
# window tested, but trading less often reliably means paying less in fees
# regardless of regime.
# trailing_stop_pct/trailing_stop_arm_pct (both optional, None = disabled):
# while holding coin, sell immediately - independent of the crossover -
# if price falls back trailing_stop_pct from its peak since the buy. If
# trailing_stop_arm_pct is also set, the stop doesn't start watching until
# price has first risen at least that %% above the BUY price, so a bad
# entry (bought right at a local spike) gets room to recover instead of
# being stopped out for a small loss the moment it wobbles.
#
# Backtested against real historical data before enabling anything here
# (see backtest.py --trailing-stop/--trailing-stop-arm): the 1h values
# below improved BOTH return and max drawdown over the 30-day window
# tested, a genuinely low-regret result, not just a threshold that
# happened to look good once. 5m and 1d showed no similarly robust
# benefit on the data available at the time, so left disabled - revisit
# once each bot's own live history is long enough to test against.
#
# fee_aware_multiple (optional, None = disabled): skip a buy/sell if price
# hasn't moved at least this multiple of the round-trip fee cost since the
# bot's LAST TRADE. Targets whipsaw specifically - reversing a position at
# close to the same price, paying the fee twice for essentially no move.
#
# Backtested per-bot before enabling (see backtest.py --fee-aware): 5m
# showed a clear, consistent improvement across every period pair and
# multiple tested (fees are a much bigger fraction of a 5-minute candle's
# typical move), so it's enabled here at 1.0x - exactly the round-trip fee
# cost, a principled threshold rather than whichever backtest number
# happened to look best. 1h showed a smaller but still real improvement at
# low multiples (0.5x barely changed the return while roughly halving fees
# paid) - higher multiples looked better on paper but collapsed to only 2
# trades, the same "looks great because there's almost no sample left"
# pattern that got the 1d trailing-stop result discarded, so 1h is enabled
# conservatively at 0.5x rather than chasing that number. 1d showed no
# benefit - daily moves already usually clear the fee threshold on their
# own, so the filter barely triggers and occasionally cut a rare, large
# winning trade instead - left disabled.
BOTS = {
    "5m": {
        "label": "5-minute candles",
        "interval_minutes": 5,
        "short_period": 12,
        "long_period": 26,
        "trailing_stop_pct": None,
        "trailing_stop_arm_pct": None,
        "fee_aware_multiple": 1.0,
    },
    "1h": {
        "label": "Hourly candles",
        "interval_minutes": 60,
        "short_period": 12,
        "long_period": 26,
        "trailing_stop_pct": 1.0,
        "trailing_stop_arm_pct": 0.75,
        "fee_aware_multiple": 0.5,
    },
    "1d": {
        "label": "Daily candles",
        "interval_minutes": 1440,
        "short_period": 12,
        "long_period": 26,
        "trailing_stop_pct": None,
        "trailing_stop_arm_pct": None,
        "fee_aware_multiple": None,
    },
}
DEFAULT_BOT = "5m"


def bot_files(bot_key: str) -> dict:
    """File paths for one bot's state - kept separate per bot so they never
    collide or interfere with each other."""
    return {
        "ledger": f"ledger_{bot_key}.json",
        "history": f"history_{bot_key}.csv",
        "log": f"trades_{bot_key}.log",
    }


# --- Paper trading ---
STARTING_BALANCE_GBP = 100.0

# Kraken's standard taker fee at the lowest 30-day volume tier is 0.26% as of
# writing - this bot trades on signals (effectively a market order), so taker
# fee is the realistic assumption. Fees drop at higher volume tiers, and
# Kraken can change its fee schedule - check https://www.kraken.com/features/fee-schedule
# and update this if you want the simulation to stay accurate.
TRADING_FEE_PCT = 0.0026

# --- UK Capital Gains Tax assumptions (see uk_tax.py for what this does and
# does NOT model - it's an illustrative estimate, not tax advice) ---
# Annual tax-free allowance for capital gains, 2024/25 tax year onward.
# This has been cut sharply in recent years (£12,300 -> £6,000 -> £3,000)
# and could change again in a future Budget - verify the current figure at
# https://www.gov.uk/capital-gains-tax/allowances before trusting this.
CGT_ANNUAL_EXEMPT_AMOUNT_GBP = 3000.0

# CGT rate on gains from assets other than residential property, since the
# rate rise on 30 October 2024: 18% for basic-rate taxpayers, 24% for
# higher/additional-rate taxpayers. Which one applies depends on YOUR total
# taxable income for the year (this bot has no way to know that) - set this
# to whichever band actually applies to you. Defaulted to the higher rate
# here as a stated assumption, not a calculation - confirm your own band
# at https://www.gov.uk/capital-gains-tax/rates.
CGT_RATE = 0.24

# --- Loop timing (local/manual continuous runs only - railway_worker.py
# uses its own CHECK_INTERVAL_SECONDS per bot instead) ---
CHECK_INTERVAL_SECONDS = 300

# --- Safety switch ---
# This MUST stay True until you have read README.md's "Going live" section,
# understand the risks, and have deliberately wired up real order execution.
# Nothing in this codebase will place a real order while this is True.
PAPER_MODE = True

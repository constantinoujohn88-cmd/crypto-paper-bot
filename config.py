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
BOTS = {
    "5m": {
        "label": "5-minute candles",
        "interval_minutes": 5,
        "short_period": 12,
        "long_period": 26,
    },
    "1h": {
        "label": "Hourly candles",
        "interval_minutes": 60,
        "short_period": 12,
        "long_period": 26,
    },
    "1d": {
        "label": "Daily candles",
        "interval_minutes": 1440,
        "short_period": 12,
        "long_period": 26,
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

# --- Loop timing (local/manual continuous runs only - GitHub Actions uses
# --once and its own per-bot cron schedule instead) ---
CHECK_INTERVAL_SECONDS = 300

# --- Safety switch ---
# This MUST stay True until you have read README.md's "Going live" section,
# understand the risks, and have deliberately wired up real order execution.
# Nothing in this codebase will place a real order while this is True.
PAPER_MODE = True

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

# --- Loop timing (local/manual continuous runs only - GitHub Actions uses
# --once and its own per-bot cron schedule instead) ---
CHECK_INTERVAL_SECONDS = 300

# --- Safety switch ---
# This MUST stay True until you have read README.md's "Going live" section,
# understand the risks, and have deliberately wired up real order execution.
# Nothing in this codebase will place a real order while this is True.
PAPER_MODE = True

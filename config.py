"""
Central config. Change these values to tune the bot.
"""

# --- Market ---
KRAKEN_PAIR = "XBTGBP"          # BTC/GBP on Kraken. See https://api.kraken.com/0/public/AssetPairs
OHLC_INTERVAL_MINUTES = 5       # candle size Kraken returns (1, 5, 15, 30, 60, ...)

# --- Strategy: moving average crossover ---
SHORT_MA_PERIOD = 12            # ~1 hour of 5-min candles
LONG_MA_PERIOD = 26             # ~2h10m of 5-min candles

# --- Paper trading ---
STARTING_BALANCE_GBP = 100.0
LEDGER_FILE = "ledger.json"
LOG_FILE = "trades.log"
HISTORY_FILE = "history.csv"    # per-check price/portfolio snapshots, for the dashboard

# Kraken's standard taker fee at the lowest 30-day volume tier is 0.26% as of
# writing - this bot trades on signals (effectively a market order), so taker
# fee is the realistic assumption. Fees drop at higher volume tiers, and
# Kraken can change its fee schedule - check https://www.kraken.com/features/fee-schedule
# and update this if you want the simulation to stay accurate.
TRADING_FEE_PCT = 0.0026

# --- Loop timing ---
CHECK_INTERVAL_SECONDS = 300    # how often the bot checks the market (5 min)

# --- Safety switch ---
# This MUST stay True until you have read README.md's "Going live" section,
# understand the risks, and have deliberately wired up real order execution.
# Nothing in this codebase will place a real order while this is True.
PAPER_MODE = True

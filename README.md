# Crypto Paper Trading Bot

A starter bot that simulates trading BTC/GBP using live Kraken prices and a
simple moving-average crossover strategy. It starts with a virtual £100 and
never touches real money unless you deliberately change that (see below).

## What it does

Every 5 minutes (configurable), the bot:
1. Pulls recent BTC/GBP price candles from Kraken's public API
2. Computes a short-term and long-term moving average
3. If the short average crosses above the long average → simulated **buy**
4. If it crosses below → simulated **sell**
5. Logs the decision and, if a trade happened, updates a local ledger file

Nothing here places a real order. `config.PAPER_MODE = True` by default, and
`main.py` will refuse to go further than logging a warning if you turn it off
without also implementing `place_live_order()`.

## Running it

This bot is designed to run on **GitHub Actions**, not on your own machine:
a scheduled workflow (`.github/workflows/paper-trade.yml`) runs one check
every 5 minutes, forever, for free, without a server or a terminal window
staying open. Each run commits the updated `ledger.json` and `history.csv`
back to the repo, so the trade history is versioned in git.

To run it locally instead (e.g. to test changes before pushing):

```bash
cd crypto-paper-bot
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py           # loops forever, checking every CHECK_INTERVAL_SECONDS
python main.py --once    # single check and exit (what GitHub Actions uses)
```

## Files

| File | Purpose |
|---|---|
| `config.py` | All the settings you're likely to want to change |
| `data_fetcher.py` | Pulls price data from Kraken's public (no-auth) API |
| `strategy.py` | The moving-average crossover logic — swap this out to try other strategies |
| `ledger.py` | Tracks the simulated balance, holdings, and trade history |
| `main.py` | Runs one check (`--once`) or loops forever |
| `index.html` | Static dashboard, served by GitHub Pages, reads `history.csv`/`ledger.json` |
| `.github/workflows/paper-trade.yml` | Scheduled Actions workflow that runs the bot every 5 min |

## Watching your trades

`main.py` writes a snapshot every check to `history.csv` (price, signal,
cash, holdings, portfolio value) in addition to `ledger.json` (trade
history). `index.html` is a small dashboard that reads both files directly
— no build step, no server — and is published via GitHub Pages at:

`https://<your-username>.github.io/<repo-name>/`

It shows current portfolio value/cash/holdings, price and portfolio value
charts, and tables of every trade and every check. It re-fetches the data
every 60 seconds, so refresh the page (or just leave it open) to watch it
update as Actions runs land.

## Fee assumptions

Every simulated trade deducts a fee from what you receive, the way a real
exchange does it — `config.TRADING_FEE_PCT` (0.26% by default, Kraken's
standard taker rate at the lowest volume tier). This matters more than it
sounds: a bot that trades often can lose a meaningful chunk of a small £100
balance to fees alone, even before the strategy's own performance is
considered. Total fees paid are tracked in `ledger.json` and shown on the
dashboard, so "portfolio value" always reflects the return *after* fees —
not an idealised number. If Kraken's fee schedule changes, or you move up
a volume tier, update `TRADING_FEE_PCT` to keep the simulation honest.

## Tuning the strategy

`config.py` controls:
- `SHORT_MA_PERIOD` / `LONG_MA_PERIOD` — how fast/slow the two averages react
- `OHLC_INTERVAL_MINUTES` — the candle size the averages are computed over
- `CHECK_INTERVAL_SECONDS` — how often the bot checks the market

Shorter periods react faster but trade more often (more fees if live, more
noise either way). There's no single "correct" setting — it's worth watching
`trades.log` for a few days and adjusting based on what you see.

## Going live (read this fully before doing it)

This bot is currently a simulation. To make it place real orders, you would
need to:

1. **Create a Kraken account and API key** with trading permissions, stored
   as environment variables (`KRAKEN_API_KEY`, `KRAKEN_API_SECRET`) —
   never hardcoded, never committed to git.
2. **Implement Kraken's authenticated request signing** in
   `place_live_order()` inside `main.py`. Kraken's API docs cover the
   HMAC-SHA512 signing process for private endpoints.
3. **Add safeguards** before risking real money: a maximum order size, a
   daily loss limit that halts trading, and a manual kill switch.
4. **Test with the smallest amount Kraken allows** for a while before
   scaling up, and keep watching the logs.

I'm not going to pre-write the live order execution code — a trading bot's
first real bug is best caught in paper mode, not with your money live. When
you're ready to do this step, come back and we can build and test it
carefully together, ideally with a lot more logging and a dry-run mode first.

## Honest expectations

- £100 is a very small amount relative to fees, spreads, and normal price
  swings — treat this as a learning project, not an income source.
- A moving-average crossover is simple and easy to reason about, but it's a
  well-known, widely-used strategy with no guaranteed edge. Backtested or
  simulated performance is not a promise of future results.
- This isn't financial advice — it's a tool for you to observe and learn from.

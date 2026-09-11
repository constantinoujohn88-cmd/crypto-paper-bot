# Crypto Paper Trading Bots

Three bots that simulate trading BTC/GBP using live Kraken prices and the
same moving-average crossover strategy - the only difference between them
is how often they check the market. Each starts with its own virtual £100
and never touches real money unless you deliberately change that (see
below).

## What it does

Each bot, on its own schedule:
1. Pulls recent BTC/GBP price candles from Kraken's public API
2. Computes a short-term and long-term moving average
3. If the short average crosses above the long average → simulated **buy**
4. If it crosses below → simulated **sell**
5. Logs the decision and, if a trade happened, updates its own ledger file

Nothing here places a real order. `config.PAPER_MODE = True` by default, and
`main.py` will refuse to go further than logging a warning if you turn it off
without also implementing `place_live_order()`.

## Why three bots

`config.BOTS` defines three independent bots with **identical** strategy
periods (12/26 moving average) but different candle cadences:

| Bot | Candle size | Roughly |
|---|---|---|
| `5m` | 5 minutes | reacts fast, checks constantly |
| `1h` | 1 hour | reacts to hourly trends |
| `1d` | 1 day | reacts to multi-day trends |

Keeping the periods identical and varying only the cadence isolates one
question cleanly: does trading frequency alone change the outcome? See
`backtest.py` below - the honest answer, from real historical data, is
"it depends on the market regime, but faster trading reliably means paying
more in fees regardless of regime."

## Running it

This is designed to run on **GitHub Actions**, not on your own machine: three
scheduled workflows (`.github/workflows/paper-trade-5m.yml`, `-1h.yml`,
`-1d.yml`) each run one bot's check on its own cadence, forever, for free,
without a server or a terminal window staying open. Each run commits that
bot's updated `ledger_<bot>.json` and `history_<bot>.csv` back to the repo,
so the trade history is versioned in git.

To run one locally instead (e.g. to test changes before pushing):

```bash
cd crypto-paper-bot
python3 -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py --bot 1h           # loops forever, checking every CHECK_INTERVAL_SECONDS
python main.py --bot 1h --once    # single check and exit (what GitHub Actions uses)
```

`--bot` is one of `5m`, `1h`, `1d` (defaults to `5m`).

## Files

| File | Purpose |
|---|---|
| `config.py` | Bot definitions (`BOTS`) and all the settings you're likely to want to change |
| `data_fetcher.py` | Pulls price data from Kraken's public (no-auth) API |
| `strategy.py` | The moving-average crossover logic — swap this out to try other strategies |
| `ledger.py` | Tracks a simulated balance, holdings, and trade history |
| `uk_tax.py` | Illustrative UK Capital Gains Tax estimate on realised gains (not tax advice) |
| `main.py` | Runs one bot's check (`--bot <key> --once`) or loops forever |
| `export_tax_csv.py` | Exports a bot's trades as a CSV formatted for a tax tool/accountant |
| `reconcile.py` | Matches the ledger against a real Kraken trade export - for if you ever go live |
| `backtest.py` | Tests the strategy against real historical prices instead of guessing at settings |
| `index.html` | Static dashboard, served by GitHub Pages, comparing all three bots |
| `.github/workflows/paper-trade-*.yml` | Scheduled Actions workflows, one per bot, on that bot's own cadence |

## Watching your trades

Each bot writes a snapshot every check to its own `history_<bot>.csv`
(price, moving averages, signal, cash, holdings, portfolio value) in
addition to `ledger_<bot>.json` (trade history). `index.html` is a
dashboard that reads all three bots' files directly - no build step, no
server - and is published via GitHub Pages at:

`https://<your-username>.github.io/<repo-name>/`

It shows a side-by-side comparison (portfolio value chart with all three
bots overlaid, one line each) plus a per-bot detail view (price + moving
averages + buy/sell markers, portfolio value, trade history, recent
checks) behind tabs. It re-fetches the data every 60 seconds, so refresh
the page (or just leave it open) to watch it update as Actions runs land.

## Backtesting before you trust a config

`backtest.py` replays the *exact same* strategy and fee logic against real
historical Kraken prices, instead of guessing at settings:

```bash
python backtest.py --bot 1h              # test the hourly bot's cadence
python backtest.py --bot 1d --source history   # test against this repo's own accumulated data
```

Kraken's public API always caps a request at ~720 candles regardless of
candle size, so bigger candles buy a longer look-back at the cost of
coarser signals: 5-minute candles get ~2.5 days of history, hourly gets
~30 days, daily gets ~2 years. Worth knowing before trusting any single
backtest: which parameter set "wins" can flip completely depending on the
window and market regime tested - a fast config that loses badly in a
choppy 3-day window can be the best performer over 2 years, and vice
versa. The one thing that holds up consistently across every window
tested: trading less often reliably means paying less in fees. That's
arithmetic, not a market call.

## Trailing stops (an early exit, on top of the crossover)

The crossover sell can lag badly: a delayed check can mean the bot rides
a position most of the way back down before the long-term average
confirms a reversal. `config.BOTS[<key>]` optionally sets `trailing_stop_pct`:
while holding coin, the bot tracks the highest price seen since the buy
and sells immediately - independent of the crossover - if price falls
back that %% from the peak. The original crossover sell is still there
as a fallback for whenever the trailing stop doesn't fire.

`trailing_stop_arm_pct` refines this further: the stop doesn't start
watching for a pullback until price has first risen at least that %%
above the *buy* price. Without it, a bad entry (bought right at a local
spike, which - see the project's own history - has happened) gets
stopped out for a small loss the moment it wobbles, with no chance to
recover. With it, a bad entry is simply not protected yet (only the
crossover sell can exit it) until it's actually shown a real gain worth
protecting.

Backtested before enabling anything (`backtest.py --trailing-stop N
[--trailing-stop-arm N]`) - only the hourly bot has this turned on
(1%/0.75% arm), because it's the only one where backtesting showed a
result that improved *both* return and max drawdown over the tested
window, not just one at the other's expense. The 5-minute and daily bots
showed no similarly robust benefit on the data available at the time
(one gave a result that looked good in isolation but fell apart under a
proper sweep of nearby values - a reminder of exactly the overfitting
risk this whole project keeps running into) - left disabled rather than
guess, revisit once each has enough of its own live history to test
against properly.

## UK tax (illustrative, not advice)

**This is not tax advice.** `uk_tax.py` models UK Capital Gains Tax as an
estimate so you can see roughly what HMRC would take from a strategy's
gains - not a number to file a return from. Every disposal (sell) is
matched against the buy it closes out, the gain is `net sale proceeds -
original cost`, and gains/losses are netted per UK tax year (6 April - 5
April) against `config.CGT_ANNUAL_EXEMPT_AMOUNT_GBP` and taxed at
`config.CGT_RATE`.

What this deliberately doesn't cover - read `uk_tax.py`'s docstring for
the full list, but the headlines:
- **Assumes CGT, not Income Tax.** HMRC can classify very frequent,
  organised trading as Income Tax instead - exactly the kind of pattern an
  automated bot produces. This model doesn't attempt that classification.
- **No share-pooling/bed-and-breakfast rules.** Not needed here specifically
  *because* each bot only ever holds 100% cash or 100% coin, never a
  partial position - a strategy with partial buys/sells would need HMRC's
  full same-day/30-day matching rules, which aren't implemented.
- **No loss carry-forward** between tax years.
- **Rate and allowance are your own assumptions**, not something the bot
  can determine - it doesn't know your income, tax band, or other capital
  gains. Verify current figures at gov.uk before trusting them; both
  change most tax years.
- **Each bot's allowance is modelled independently** - combine their gains
  yourself if you want the "one real allowance across everything" picture.

The dashboard shows an estimated tax owed and an "after tax" portfolio
value per bot, both computed from these assumptions and clearly labelled
as illustrative. It also shows two running totals that update with every
trade, straight from the ledger rather than needing to be worked out by
hand afterwards: **gross disposal proceeds** (total sale value across all
sells, before the sell-side fee - the figure most tax worksheets ask for)
and **net realised gain** (actual profit/loss after both buy- and
sell-side costs, summed across every tax year).

### Exporting for a tax tool or accountant

The dashboard itself has "Export CSV" buttons - one per bot (in that bot's
Trade History panel) and one for all three bots combined (top of the
Compare cadences section) - that download directly from your browser, no
Python needed. Or run it locally for the same file:

```bash
python export_tax_csv.py --bot 5m    # one bot  -> tax_export_5m.csv
python export_tax_csv.py --bot all   # all bots, combined and time-sorted -> tax_export.csv
```

Both produce identical output: a CSV with `timestamp, action, amount,
price_gbp, fee_gbp` plus the gross/net value and capital gain per disposal
already computed - the part that's normally the tedious bit when starting
from a raw exchange export. Column names are generic rather than matching
one specific tool's import template; you may need to rename/remap columns
for whichever tool you actually use.

### Reconciling against Kraken (for if you ever go live)

Not useful today - paper mode never touches a real Kraken account, so
there's nothing real to check the ledger against. If you ever wire up
real trading, `reconcile.py` compares the bot's ledger against a real
trade history export downloaded from Kraken (Account → Export → Trades)
and flags anything that doesn't line up:

```bash
python reconcile.py --bot 5m --kraken-export kraken_trades.csv
```

It groups Kraken's export by order ID first, since a single order can fill
across several rows at slightly different prices if the order book didn't
have the depth for one clean fill - those get combined into one
volume-weighted trade before comparing, matching how the bot's ledger
already records one row per buy/sell regardless of how it filled. Matches
are found by nearest timestamp (within `--tolerance-minutes`, default 5)
between trades of the same type, and it reports three things: trades that
matched (flagging any price/volume/fee difference beyond a penny), trades
the bot logged that Kraken has no record of, and trades Kraken executed
that the bot doesn't know about - any of the latter two would mean
something is actually wrong, not just noisy.

## Fee assumptions

Every simulated trade deducts a fee from what you receive, the way a real
exchange does it — `config.TRADING_FEE_PCT` (0.26% by default, Kraken's
standard taker rate at the lowest volume tier). This matters more than it
sounds: a bot that trades often can lose a meaningful chunk of a small £100
balance to fees alone, even before the strategy's own performance is
considered. Total fees paid are tracked in each `ledger_<bot>.json` and shown on the
dashboard, so "portfolio value" always reflects the return *after* fees —
not an idealised number. If Kraken's fee schedule changes, or you move up
a volume tier, update `TRADING_FEE_PCT` to keep the simulation honest.

## Tuning the strategy

`config.BOTS[<key>]` controls, per bot:
- `short_period` / `long_period` — how fast/slow the two averages react
- `interval_minutes` — the candle size the averages are computed over

`CHECK_INTERVAL_SECONDS` (shared) controls how often a *local* continuous
run checks the market - GitHub Actions ignores this and uses each
workflow's own cron schedule instead.

Shorter periods and smaller candles react faster but trade more often (more
fees, more noise). There's no single "correct" setting - see the
Backtesting section above rather than guessing, and watch `trades_<bot>.log`
for a few days before adjusting anything.

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

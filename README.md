# Crypto Paper Trading Bots

Four bots that simulate trading BTC/GBP using live Kraken prices. Three
share the same moving-average crossover strategy and differ only in how
often they check the market; a fourth adds an experimental early-entry
variant at the fastest cadence (see "Why four bots" below). Each starts
with its own virtual £100 and never touches real money unless you
deliberately change that (see below).

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

## Why four bots

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

A 4th bot, `5m-hybrid`, sits outside that comparison on purpose - same
cadence and periods as `5m`, its own independent £100, but with the
breakout hybrid entry from the "Breakout hybrid entry" section below
enabled. It exists to answer a different question: does buying
immediately on a fast price move (instead of waiting for the crossover to
confirm it) actually help, tested with real money-shaped stakes over
real time, alongside the plain `5m` bot it's compared against under
identical market conditions.

## Running it

Two ways to run this continuously, plus a way to run one bot locally.

### Running it: Railway

GitHub Actions' `schedule` trigger is best-effort and gets delayed under
load - this project hit that repeatedly in practice (a 5-minute cron
actually firing every ~12-18 minutes, missed crossovers, buying at the
top of a spike because the check ran late). `railway_worker.py` is a
persistent process for an always-on host like Railway: it runs all three
bots in one long-lived process, checking each on its own real internal
clock instead of waiting for an external scheduler, and pushes each
bot's updated `ledger_<bot>.json`/`history_<bot>.csv` back to git after
every check.

It also serves the dashboard directly over HTTP from the same process
(Railway's assigned `PORT`), reading the live working copy it just wrote
to - so the dashboard doesn't wait on a git push before showing a new
check. This is now the *only* place the dashboard is hosted - GitHub
Pages was dropped once Railway could serve it faster and directly, so
there's just one URL to check instead of two slightly-out-of-sync ones.

Note that Railway still depends on the GitHub **repo** itself, just not
GitHub's *hosting* or *scheduling* - `railway_worker.py` clones a fresh
working copy from it on every container start and pushes ledger/history
updates back to it after every check, because that's what makes the data
survive a redeploy or restart (Railway's own container filesystem is
thrown away each time). That's a data store, not a dependency on GitHub
Pages or Actions - both of those are gone.

To deploy:
1. Create a Railway project and service (`railway login`, `railway init`
   or `railway link` to an existing project).
2. Create a GitHub **fine-grained personal access token**
   (github.com/settings/tokens) scoped to just this repo, with
   Contents: Read and write permission - nothing broader.
3. In Railway's service settings, add two environment variables:
   - `GIT_AUTH_TOKEN` — the token from step 2
   - `GIT_REPO_URL` — `github.com/<your-username>/<repo-name>.git`
4. Generate a public domain for the service (Settings → Networking →
   Generate Domain) so the dashboard is reachable.
5. Deploy with `railway up` - builds from the `Dockerfile` (deliberately
   not relying on Railway's auto-detected Python buildpack, since neither
   Nixpacks nor Railway's newer Railpack builder include `git` by
   default, and each needs its own config format to add it - a plain
   Dockerfile sidesteps that entirely) and uploads straight from your
   local files, no GitHub involvement in the deploy itself.
6. From then on, every code change just needs `railway up` again from
   this directory - no push, no webhook, no browser click. (An earlier
   version of this setup connected Railway to the GitHub repo for
   auto-deploy instead; that hit a real snag - Railway's GitHub App was
   never properly authorized, so pushes were silently not picked up. The
   `railway up` workflow above sidesteps that failure mode entirely by
   not depending on it.)
7. There's no GitHub Actions scheduling and no GitHub Pages site anymore -
   Railway is the only thing checking the bots and the only place the
   dashboard is served from, so there's no duplicate/competing pushes to
   the same repo and no second, lagging copy of the dashboard to keep in
   sync.

### Running one bot locally (for testing changes before deploying)

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
| `index.html` | Static dashboard comparing all four bots, served directly by `railway_worker.py` |
| `railway_worker.py` | Persistent scheduler for Railway (or similar) - runs all four bots on a real internal clock, and serves `index.html` |
| `Dockerfile` | Builds a container with `git` installed and runs `railway_worker.py` - used instead of Railway's auto-detected Python buildpack, which doesn't include git under either Nixpacks or Railpack |

## Watching your trades

Each bot writes a snapshot every check to its own `history_<bot>.csv`
(price, moving averages, signal, cash, holdings, portfolio value) in
addition to `ledger_<bot>.json` (trade history). `index.html` is a
dashboard that reads all four bots' files directly - no build step -
and is served by `railway_worker.py` itself at whatever domain you
generated in Railway (Settings → Networking → Generate Domain).

It shows a side-by-side comparison (portfolio value chart with all four
bots overlaid, one line each) plus a per-bot detail view (price + moving
averages + buy/sell markers, portfolio value, trade history, recent
checks) behind tabs, each with 1H/6H/24H/7D/30D/All zoom controls so
recent movement stays visible instead of flattening out against months
of history. It re-fetches the data every 60 seconds, so refresh the page
(or just leave it open) to watch it update as checks land.

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

## Fee-aware trade filter (skipping trades too small to be worth the fee)

The crossover strategy is otherwise fee-blind: it trades on every
crossover regardless of how small the resulting move is, even though
every round trip pays `TRADING_FEE_PCT` twice (once in, once out). In a
choppy, sideways market that means whipsawing - reversing a position at
close to the same price it was opened at, paying the fee twice for
essentially no move. `config.BOTS[<key>]` optionally sets
`fee_aware_multiple`: a buy/sell is skipped if price hasn't moved at
least this multiple of the round-trip fee cost since the bot's *last
trade*. A skipped signal is simply forgone, not retried - the crossover
tracking moves on regardless.

Backtested per-bot before enabling (`backtest.py --fee-aware N`): the
5-minute bot showed a clear, consistent improvement across every period
pair and multiple tested - unsurprising, since fees are a much bigger
fraction of a 5-minute candle's typical move - so it's enabled there at
1.0x, exactly the round-trip fee cost. The hourly bot showed a smaller
but genuine improvement at low multiples (0.5x barely changed the return
while roughly halving fees paid); higher multiples looked better on
paper but did so by cutting the trade count down to 2, the same "looks
great because there's almost no sample left" pattern the trailing-stop
section above already flagged as overfitting - so the hourly bot is
enabled conservatively at 0.5x rather than chasing that number. The
daily bot showed no benefit (daily moves already usually clear the fee
threshold on their own, so the filter barely triggers, and when it did
it once cut a rare, large winning trade) - left disabled.

An earlier version of this filter compared the %% gap between the short
and long MA at the moment of crossover instead of price-since-last-trade
- worth knowing if you're extending this, since it's a dead end: a
crossover is *by definition* the point where the two averages are equal,
so that gap is always ~0 exactly when a signal fires, and the filter
ended up rejecting virtually every trade regardless of the threshold.
Caught by testing against real data before drawing any conclusions from
it - the version described above is what actually shipped.

## Breakout hybrid entry (buying before the crossover confirms)

The crossover strategy is a *confirmation* strategy by design: it only
buys once the short MA has actually caught up and crossed the long MA,
which means it always misses the first leg of a fast move. That lag is
also what protects it from whipsawing on every false spike - a
deliberate trade-off, not a bug (see `strategy.py`'s docstring). If you'd
rather catch the move earlier at the cost of more false starts,
`config.BOTS[<key>]` optionally sets `breakout_lookback`: while in cash,
the bot buys immediately - independent of the crossover - the moment
price closes above the highest price of the preceding `breakout_lookback`
candles. The crossover buy still exists as a fallback for slower-building
trends that never produce a sharp breakout, and the fee-aware filter
above still applies to a breakout-triggered buy exactly as it would to a
crossover one.

Backtested first (`backtest.py --breakout N --fee-aware 1.0`, since
that's what actually runs together): every lookback tested (6/12/24/48
candles) improved on the plain 5-minute bot's own currently-deployed
result for the 12/26 period pair, best at 12 candles (a 1-hour lookback).
But that's only 2-3 actual breakout trades across the ~2.5 days of data
Kraken's API gives us for 5-minute candles - a thinner sample than what
justified the fee-aware filter, and it made things *worse* when tested
against other period pairs (12/50, 20/50). Genuinely unproven either way.

Rather than edit the plain `5m` bot on that thin evidence, it runs as its
own bot instead: `5m-hybrid`, same cadence and periods as `5m`, its own
independent £100, `fee_aware_multiple: 1.0` and `breakout_lookback: 12`.
It exists to accumulate real, independent evidence over time by running
alongside `5m` under identical market conditions, rather than gambling
the config a stronger backtest already justified.

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
Trade History panel) and one for all four bots combined (top of the
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

`CHECK_INTERVAL_SECONDS` (shared, also used by `railway_worker.py`)
controls how often a continuous run checks the market for each bot.

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

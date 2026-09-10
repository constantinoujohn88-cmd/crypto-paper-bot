"""
Rough UK Capital Gains Tax (CGT) modelling for the paper trading bots.

THIS IS NOT TAX ADVICE. It's an illustrative estimate so you can see roughly
how much of a strategy's gains HMRC would actually take, not a number to
file a tax return from. Real UK crypto tax has more nuance than this
covers - see the simplifications below, and verify anything that matters
at gov.uk before relying on it for anything real.

How this models it, and what it deliberately simplifies:

- HMRC taxes cryptoasset disposals by individuals as Capital Gains Tax (not
  Income Tax) in the large majority of retail cases. Very frequent,
  business-like, organised trading COULD instead be classed as Income Tax -
  and an automated bot trading on a fixed schedule is exactly the kind of
  pattern where that classification is least certain. This model assumes
  CGT throughout. If this were ever real trading, get that classification
  checked properly rather than assuming it.

- Each bot here always holds either 100% cash or 100% coin - it never buys
  again before selling what it already holds, and never holds a partial
  position. That means there's no need for HMRC's share-pooling / "same
  day" and "30 day" (bed-and-breakfast) matching rules that apply when you
  have multiple overlapping purchase lots of the same asset: here, every
  sell disposes of exactly one preceding buy, so the realised gain per
  round trip is simply (net sale proceeds) - (original cost, including the
  buy-side fee). A trading pattern with partial buys/sells or repeated
  top-ups would need the full pooling rules, which this does not
  implement.

- Gains and losses are netted within each UK tax year (6 April - 5 April).
  A net loss in a year means no tax is owed that year, but this does not
  model carrying that loss forward to offset a future year's gains, which
  real UK tax law allows.

- The tax-free Annual Exempt Amount and the CGT rate are both assumptions
  set in config.py (CGT_ANNUAL_EXEMPT_AMOUNT_GBP, CGT_RATE) - the bot has
  no way to know your personal tax band, your other income, or any other
  capital gains you have outside this project. Verify current figures at
  https://www.gov.uk/capital-gains-tax/rates and https://www.gov.uk/capital-gains-tax/allowances
  before trusting them; both change most tax years.

- Each bot's allowance is modelled independently, as if it were the only
  capital gain you had. If you ran all three for real with real money,
  HMRC would combine their gains (and any of your other capital gains)
  against a single shared Annual Exempt Amount, not one each.
"""
from datetime import datetime


def uk_tax_year(iso_timestamp: str) -> str:
    """Returns e.g. '2026/27' for the UK tax year (6 April - 5 April) that
    an ISO timestamp falls in."""
    d = datetime.fromisoformat(iso_timestamp).date()
    start_year = d.year if (d.month, d.day) >= (4, 6) else d.year - 1
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def estimate_tax(realized_gains_by_year: dict, exempt_amount: float, rate: float) -> dict:
    """realized_gains_by_year: {tax_year_str: net_gain_or_loss_gbp}.

    Returns the same years, each with {gain, taxable_gain, estimated_tax},
    plus a 'total' row summing across all years. A net loss in a year
    yields taxable_gain 0 and estimated_tax 0 (see module docstring - loss
    carry-forward to other years isn't modelled).
    """
    result = {}
    total_gain = 0.0
    total_tax = 0.0
    for year, gain in sorted(realized_gains_by_year.items()):
        taxable = max(0.0, gain - exempt_amount)
        tax = taxable * rate
        result[year] = {"gain": gain, "taxable_gain": taxable, "estimated_tax": tax}
        total_gain += gain
        total_tax += tax
    result["total"] = {"gain": total_gain, "taxable_gain": None, "estimated_tax": total_tax}
    return result

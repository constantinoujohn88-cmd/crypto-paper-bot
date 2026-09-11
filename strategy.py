"""
Strategy logic. Currently: simple moving average (SMA) crossover.

Signal logic:
- "buy"  when the short MA crosses ABOVE the long MA (upward momentum starting)
- "sell" when the short MA crosses BELOW the long MA (downward momentum starting)
- "hold" otherwise, or if there isn't enough price history yet

This is a well-known, easy-to-reason-about strategy - not a claim that it's
profitable. It tends to lag fast reversals and can whipsaw in choppy markets.
Swap this file out for a different strategy without touching the rest of the bot.

Crossover detection compares against the relationship recorded at the
PREVIOUS CHECK (passed in by the caller, persisted in the ledger) rather
than against one candle back in the current price fetch. This matters
because checks don't reliably happen every candle - a scheduled check can
be delayed, and several candles can form in the gap. Comparing only the
two most recent candles in a single fetch will miss a crossover that
already happened and resolved somewhere in that gap, because by the time
you look, both "now" and "one candle back" can already be on the same
side. Comparing against what was last actually observed catches a
crossover as long as it happened since the last check, no matter how many
candles occurred in between.
"""


def _sma(prices: list[float], period: int) -> float:
    return sum(prices[-period:]) / period


def moving_averages(prices: list[float], short_period: int, long_period: int):
    """Returns (short_ma, long_ma), or (None, None) if there isn't yet
    enough price history for the long average."""
    if len(prices) < long_period:
        return None, None
    return _sma(prices, short_period), _sma(prices, long_period)


def relationship(short_ma: float | None, long_ma: float | None) -> str | None:
    """'above', 'below', or None if an average isn't available yet."""
    if short_ma is None or long_ma is None:
        return None
    return "above" if short_ma >= long_ma else "below"


def compute_signal(short_ma: float | None, long_ma: float | None, prev_relationship: str | None):
    """
    Returns (signal, current_relationship). The caller is responsible for
    persisting current_relationship and passing it back in as
    prev_relationship on the next check - that's what makes this robust to
    irregular check timing (see module docstring).

    "hold" whenever either average isn't available yet, or there's no
    prior relationship to compare against (e.g. the very first check).
    """
    current = relationship(short_ma, long_ma)
    if current is None or prev_relationship is None:
        return "hold", current

    if current == "above" and prev_relationship == "below":
        signal = "buy"
    elif current == "below" and prev_relationship == "above":
        signal = "sell"
    else:
        signal = "hold"

    return signal, current

"""
Strategy logic. Currently: simple moving average (SMA) crossover.

Signal logic:
- "buy"  when the short MA crosses ABOVE the long MA (upward momentum starting)
- "sell" when the short MA crosses BELOW the long MA (downward momentum starting)
- "hold" otherwise, or if there isn't enough price history yet

This is a well-known, easy-to-reason-about strategy - not a claim that it's
profitable. It tends to lag fast reversals and can whipsaw in choppy markets.
Swap this file out for a different strategy without touching the rest of the bot.
"""


def _sma(prices: list[float], period: int) -> float:
    return sum(prices[-period:]) / period


def compute_signal(prices: list[float], short_period: int, long_period: int) -> str:
    """
    prices: closing prices, oldest first, most recent last.
    Needs at least long_period + 1 prices to detect a crossover.
    """
    if len(prices) < long_period + 1:
        return "hold"

    short_now = _sma(prices, short_period)
    long_now = _sma(prices, long_period)

    short_prev = _sma(prices[:-1], short_period)
    long_prev = _sma(prices[:-1], long_period)

    crossed_up = short_prev <= long_prev and short_now > long_now
    crossed_down = short_prev >= long_prev and short_now < long_now

    if crossed_up:
        return "buy"
    if crossed_down:
        return "sell"
    return "hold"

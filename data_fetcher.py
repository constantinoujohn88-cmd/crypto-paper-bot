"""
Pulls price data from Kraken's public API. No API key required for this -
public market data is open to anyone.
"""
import requests

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
KRAKEN_TICKER_URL = "https://api.kraken.com/0/public/Ticker"


def get_recent_closes(pair: str, interval_minutes: int, count: int = 100) -> list[float]:
    """
    Returns a list of recent candle closing prices, oldest first.
    Raises RuntimeError if Kraken returns an error or unexpected shape.
    """
    resp = requests.get(
        KRAKEN_OHLC_URL,
        params={"pair": pair, "interval": interval_minutes},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"Kraken OHLC error: {data['error']}")

    result = data.get("result", {})
    # The pair key in the response isn't always identical to the request
    # (e.g. "XBTGBP" vs "XXBTZGBP"), so grab the first non-"last" key.
    series_key = next(k for k in result.keys() if k != "last")
    candles = result[series_key]

    # Each candle: [time, open, high, low, close, vwap, volume, count]
    closes = [float(candle[4]) for candle in candles]
    return closes[-count:]


def get_current_price(pair: str) -> float:
    """Returns the latest traded price for the pair."""
    resp = requests.get(KRAKEN_TICKER_URL, params={"pair": pair}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    if data.get("error"):
        raise RuntimeError(f"Kraken Ticker error: {data['error']}")

    result = data.get("result", {})
    series_key = next(iter(result.keys()))
    last_trade_price = result[series_key]["c"][0]
    return float(last_trade_price)

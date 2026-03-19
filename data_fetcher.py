from __future__ import annotations

import time
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

log = logging.getLogger("rsi-bot.data")
DEFAULT_PROVIDER = os.environ.get("MARKET_DATA_PROVIDER", "auto").strip().lower()


@dataclass
class MarketSnapshot:
    symbol: str
    timeframe: str
    data: pd.DataFrame
    source: str = "yfinance"


_CACHE: dict[tuple[str, str, str], tuple[float, MarketSnapshot]] = {}
_CACHE_TTL_SECONDS = 180


def _cache_key(symbol: str, period: str, interval: str) -> tuple[str, str, str]:
    return (symbol.upper(), period, interval)


def _download_ohlcv(symbol: str, period: str, interval: str, retries: int = 3) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False)
            if df is None or df.empty:
                raise ValueError(f"No market data returned for {symbol}")
            return df.rename(columns=str.title)
        except YFRateLimitError as exc:
            last_error = exc
            if attempt + 1 == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:
            last_error = exc
            if attempt + 1 == retries:
                raise
            time.sleep(0.8 * (attempt + 1))
    if last_error:
        raise last_error
    raise ValueError(f"Failed to download data for {symbol}")


def _download_stooq(symbol: str) -> pd.DataFrame:
    base = symbol.upper()
    if base.endswith("-USD"):
        raise ValueError("Stooq fallback is not available for crypto symbols")

    stooq_symbol = base.lower()
    if "." not in stooq_symbol:
        stooq_symbol = f"{stooq_symbol}.us"
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    df = pd.read_csv(url)
    if df is None or df.empty:
        raise ValueError(f"No Stooq data returned for {symbol}")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date")
    df = df.rename(columns=str.title)
    return df


def fetch_ohlcv(symbol: str, period: str = "6mo", interval: str = "1d") -> MarketSnapshot:
    key = _cache_key(symbol, period, interval)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    provider_order = ["yfinance", "stooq"]
    if DEFAULT_PROVIDER == "yfinance":
        provider_order = ["yfinance"]
    elif DEFAULT_PROVIDER == "stooq":
        provider_order = ["stooq"]

    df = None
    source = None
    last_error: Exception | None = None
    for provider in provider_order:
        try:
            if provider == "yfinance":
                df = _download_ohlcv(symbol, period, interval)
                source = "yfinance"
            elif provider == "stooq":
                if interval != "1d":
                    raise ValueError("Stooq only supports daily data in this bot")
                df = _download_stooq(symbol)
                source = "stooq"
            if df is not None:
                break
        except YFRateLimitError as exc:
            last_error = exc
            log.info("yfinance rate limited for %s %s %s", symbol, period, interval)
            continue
        except Exception as exc:
            last_error = exc
            log.info("Provider %s failed for %s %s %s: %s", provider, symbol, period, interval, exc)
            continue

    if df is None or source is None:
        if last_error:
            raise last_error
        raise ValueError(f"Unable to fetch data for {symbol}")

    snapshot = MarketSnapshot(symbol=symbol.upper(), timeframe=interval, data=df, source=source)
    _CACHE[key] = (now, snapshot)
    return snapshot


def render_price_chart(df: pd.DataFrame, symbol: str, title: str, annotation: Optional[str] = None) -> BytesIO:
    fig, ax = plt.subplots(figsize=(11, 6), dpi=160)
    fig.patch.set_facecolor("#08111f")
    ax.set_facecolor("#0c1727")

    ax.plot(df.index, df["Close"], color="#7c5cff", linewidth=2.2, label="Close")
    ax.plot(df.index, df["Close"].rolling(20).mean(), color="#27e0b3", linewidth=1.6, label="SMA 20")
    ax.plot(df.index, df["Close"].rolling(50).mean(), color="#f7c948", linewidth=1.6, label="SMA 50")
    if "RSI" in df.columns:
        ax_rsi = ax.twinx()
        ax_rsi.plot(df.index, df["RSI"], color="#ff7a59", linewidth=1.2, alpha=0.8, label="RSI")
        ax_rsi.axhline(70, color="#ff7a59", alpha=0.25, linestyle="--")
        ax_rsi.axhline(30, color="#27e0b3", alpha=0.25, linestyle="--")
        ax_rsi.set_ylim(0, 100)
        ax_rsi.tick_params(colors="#c9d4e5")
        for spine in ax_rsi.spines.values():
            spine.set_color("#22314b")

    ax.set_title(f"{symbol} - {title}", color="white", fontsize=14, pad=14)
    ax.tick_params(colors="#c9d4e5")
    for spine in ax.spines.values():
        spine.set_color("#22314b")
    ax.grid(True, alpha=0.12)
    ax.legend(facecolor="#0c1727", edgecolor="#22314b", labelcolor="white")

    if annotation:
        ax.text(
            0.01,
            0.98,
            annotation,
            transform=ax.transAxes,
            va="top",
            ha="left",
            color="white",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#111c2e", edgecolor="#2b3d5c"),
        )

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def render_equity_chart(equity: pd.Series, title: str) -> BytesIO:
    fig, ax = plt.subplots(figsize=(10, 5), dpi=160)
    fig.patch.set_facecolor("#08111f")
    ax.set_facecolor("#0c1727")

    ax.plot(range(len(equity)), equity.values, color="#27e0b3", linewidth=2.2)
    ax.fill_between(range(len(equity)), equity.values, color="#27e0b3", alpha=0.12)
    ax.set_title(title, color="white", fontsize=14, pad=14)
    ax.tick_params(colors="#c9d4e5")
    for spine in ax.spines.values():
        spine.set_color("#22314b")
    ax.grid(True, alpha=0.12)

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

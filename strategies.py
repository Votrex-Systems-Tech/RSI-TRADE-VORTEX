from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import pandas as pd

from indicators import atr, ema, rsi


@dataclass
class SignalResult:
    action: str
    confidence: int
    summary: str
    details: str
    chart_title: str
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_note: str | None = None


def _latest(v: pd.Series) -> float:
    return float(v.dropna().iloc[-1])


def rsi_mean_reversion(df: pd.DataFrame) -> SignalResult:
    close = df["Close"]
    value = rsi(close)
    last = _latest(value)
    prev = float(value.dropna().iloc[-2]) if value.dropna().shape[0] > 1 else last
    price = float(close.iloc[-1])
    current_atr = float(atr(df).dropna().iloc[-1]) if not atr(df).dropna().empty else 0.0

    if last <= 30 and last > prev:
        action, confidence = "BUY", 72
        summary = "RSI вышел из перепроданности"
        entry = price
        stop_loss = price - 1.2 * current_atr if current_atr else None
        take_profit = price + 1.8 * current_atr if current_atr else None
    elif last >= 70 and last < prev:
        action, confidence = "SELL", 70
        summary = "RSI начал разворачиваться из перекупленности"
        entry = price
        stop_loss = price + 1.2 * current_atr if current_atr else None
        take_profit = price - 1.8 * current_atr if current_atr else None
    else:
        action, confidence = "WAIT", 55
        summary = "Нет чистого сигнала"
        entry = stop_loss = take_profit = None

    details = f"RSI: {last:.2f}\nЦена: {price:.2f}\nATR: {current_atr:.2f}\nЛогика: mean reversion"
    return SignalResult(
        action,
        confidence,
        summary,
        details,
        "RSI Mean Reversion",
        entry,
        stop_loss,
        take_profit,
        "Не входить без подтверждения цены" if action != "WAIT" else "Ожидание подтверждения",
    )


def ema_trend(df: pd.DataFrame) -> SignalResult:
    close = df["Close"]
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    last_close = float(close.iloc[-1])
    last20 = float(ema20.iloc[-1])
    last50 = float(ema50.iloc[-1])
    current_atr = float(atr(df).dropna().iloc[-1]) if not atr(df).dropna().empty else 0.0

    if last20 > last50 and last_close > last20:
        action, confidence = "BUY", 74
        summary = "Тренд вверх подтвержден"
        entry = last_close
        stop_loss = last_close - 1.5 * current_atr if current_atr else None
        take_profit = last_close + 2.2 * current_atr if current_atr else None
    elif last20 < last50 and last_close < last20:
        action, confidence = "SELL", 74
        summary = "Тренд вниз подтвержден"
        entry = last_close
        stop_loss = last_close + 1.5 * current_atr if current_atr else None
        take_profit = last_close - 2.2 * current_atr if current_atr else None
    else:
        action, confidence = "WAIT", 58
        summary = "Тренд не сформирован"
        entry = stop_loss = take_profit = None

    details = f"EMA20: {last20:.2f}\nEMA50: {last50:.2f}\nЦена: {last_close:.2f}\nATR: {current_atr:.2f}\nЛогика: trend following"
    return SignalResult(
        action,
        confidence,
        summary,
        details,
        "EMA Trend",
        entry,
        stop_loss,
        take_profit,
        "Сигнал требует подтверждения закрытием свечи",
    )


def breakout(df: pd.DataFrame) -> SignalResult:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    last_close = float(close.iloc[-1])
    recent_high = float(high.tail(20).max())
    recent_low = float(low.tail(20).min())
    vol = atr(df).iloc[-1]
    atr_value = float(vol) if pd.notna(vol) else 0.0

    if last_close >= recent_high * 0.995:
        action, confidence = "BUY", 69
        summary = "Пробой локального максимума"
        entry = last_close
        stop_loss = recent_low
        take_profit = last_close + (last_close - recent_low) * 1.8
    elif last_close <= recent_low * 1.005:
        action, confidence = "SELL", 69
        summary = "Пробой локального минимума"
        entry = last_close
        stop_loss = recent_high
        take_profit = last_close - (recent_high - last_close) * 1.8
    else:
        action, confidence = "WAIT", 53
        summary = "Пробой пока не подтвержден"
        entry = stop_loss = take_profit = None

    details = f"Локальный high: {recent_high:.2f}\nЛокальный low: {recent_low:.2f}\nATR: {atr_value:.2f}"
    return SignalResult(
        action,
        confidence,
        summary,
        details,
        "Breakout",
        entry,
        stop_loss,
        take_profit,
        "Пробои лучше брать только после ретеста",
    )


STRATEGIES: Dict[str, tuple[str, Callable[[pd.DataFrame], SignalResult]]] = {
    "rsi": ("RSI mean reversion", rsi_mean_reversion),
    "ema": ("EMA trend", ema_trend),
    "breakout": ("Breakout", breakout),
}

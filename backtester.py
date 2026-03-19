from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import pandas as pd

from indicators import rsi
from strategies import SignalResult


@dataclass
class BacktestResult:
    strategy_name: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    net_return_pct: float
    avg_trade_pct: float
    max_drawdown_pct: float
    equity: pd.Series
    summary: str
    commission_pct: float
    slippage_pct: float


@dataclass
class BatchBacktestResult:
    results: list[BacktestResult]
    summary: str


def _long_short_returns(entry: float, exit_price: float, action: str) -> float:
    if action == "BUY":
        return (exit_price - entry) / entry
    if action == "SELL":
        return (entry - exit_price) / entry
    return 0.0


def _apply_costs(gross_return: float, commission_pct: float, slippage_pct: float) -> float:
    cost = (commission_pct * 2) + slippage_pct
    return gross_return - cost


def _signal_at_row(strategy: Callable[[pd.DataFrame], SignalResult], df: pd.DataFrame, i: int) -> SignalResult:
    window = df.iloc[: i + 1].copy()
    window["RSI"] = rsi(window["Close"])
    return strategy(window)


def backtest_strategy(
    df: pd.DataFrame,
    strategy: Callable[[pd.DataFrame], SignalResult],
    strategy_name: str,
    lookahead_bars: int = 5,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
) -> BacktestResult:
    if len(df) < max(80, lookahead_bars + 20):
        raise ValueError("Not enough rows for backtest")

    closes = df["Close"].reset_index(drop=True)
    equity_curve = [1.0]
    wins = 0
    losses = 0
    rets: list[float] = []

    for i in range(60, len(df) - lookahead_bars):
        signal = _signal_at_row(strategy, df.reset_index(drop=True), i)
        if signal.action == "WAIT":
            equity_curve.append(equity_curve[-1])
            continue

        entry = float(closes.iloc[i])
        exit_price = float(closes.iloc[i + lookahead_bars])
        trade_ret = _long_short_returns(entry, exit_price, signal.action)
        trade_ret = _apply_costs(trade_ret * 100.0, commission_pct, slippage_pct) / 100.0
        rets.append(trade_ret)
        if trade_ret > 0:
            wins += 1
        else:
            losses += 1
        equity_curve.append(equity_curve[-1] * (1 + trade_ret))

    equity = pd.Series(equity_curve)
    rolling_max = equity.cummax()
    drawdown = (equity / rolling_max - 1.0) * 100
    max_dd = abs(float(drawdown.min())) if not drawdown.empty else 0.0
    trades = wins + losses
    win_rate = (wins / trades * 100) if trades else 0.0
    net_return_pct = (equity.iloc[-1] - 1.0) * 100 if not equity.empty else 0.0
    avg_trade_pct = (sum(rets) / len(rets) * 100) if rets else 0.0

    summary = (
        f"Trades: {trades}\n"
        f"Wins: {wins}\n"
        f"Losses: {losses}\n"
        f"Win rate: {win_rate:.1f}%\n"
        f"Net return: {net_return_pct:.2f}%\n"
        f"Avg trade: {avg_trade_pct:.2f}%\n"
        f"Max drawdown: {max_dd:.2f}%"
    )

    return BacktestResult(
        strategy_name=strategy_name,
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        net_return_pct=net_return_pct,
        avg_trade_pct=avg_trade_pct,
        max_drawdown_pct=max_dd,
        equity=equity,
        summary=summary,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )


def backtest_many(
    items: Iterable[tuple[str, pd.DataFrame]],
    strategy: Callable[[pd.DataFrame], SignalResult],
    strategy_name: str,
    lookahead_bars: int = 5,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
) -> BatchBacktestResult:
    results: list[BacktestResult] = []
    for symbol, df in items:
        result = backtest_strategy(
            df,
            strategy,
            strategy_name,
            lookahead_bars=lookahead_bars,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
        )
        results.append(result)

    if not results:
        return BatchBacktestResult(results=[], summary="No results")

    summary = "\n\n".join(
        [f"Result #{i + 1}\n{r.strategy_name}\n{r.summary}" for i, r in enumerate(results)]
    )
    return BatchBacktestResult(results=results, summary=summary)

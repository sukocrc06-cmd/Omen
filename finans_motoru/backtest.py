"""
backtest.py
-----------
Sinyal serisine göre basit long-only (isteğe bağlı short) backtest motoru.

Kurallar:
- 'AL' / 'GÜÇLÜ AL' sinyali geldiğinde ve pozisyon yoksa -> long pozisyon aç.
- 'SAT' / 'GÜÇLÜ SAT' sinyali geldiğinde ve long pozisyon varsa -> pozisyonu kapat
  (allow_short=True ise ayrıca short pozisyon aç).
- Opsiyonel stop-loss / take-profit (ATR bazlı ya da yüzde bazlı).
- Komisyon (bps) ve kayma (slippage) parametrik.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    direction: str  # 'long' | 'short'
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    reason: str | None = None
    extreme_price: float = None  # long: pozisyon açıldığından beri en yüksek fiyat, short: en düşük

    @property
    def pnl_pct(self) -> float | None:
        if self.exit_price is None:
            return None
        if self.direction == "long":
            return (self.exit_price / self.entry_price) - 1
        return (self.entry_price / self.exit_price) - 1


@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = None
    metrics: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float = 10_000.0,
    commission_bps: float = 5.0,
    allow_short: bool = False,
    stop_loss_pct: float | None = 0.03,
    take_profit_pct: float | None = None,
    trailing_atr_mult: float | None = 3.0,
) -> BacktestResult:
    """
    df: signal_engine.compute_signals() çıktısı (en az 'close', 'signal' ve
    varsa 'atr' kolonları).

    stop_loss_pct: girişten sonra sabit yüzde koruyucu stop (ör. 0.03 = %3).
    take_profit_pct: sabit yüzde kâr al hedefi (None = kapalı). VARSAYILAN
        OLARAK KAPALI: sabit bir hedef, uzun süren güçlü trendlerde kârı
        erken kilitleyip "al-tut"un çok gerisinde kalınmasına yol açar.
    trailing_atr_mult: pozisyon açıldıktan sonraki en iyi fiyattan ATR'nin
        kaç katı geriye düşülünce çıkılacağını belirler (chandelier exit).
        Bu, trend sürdüğü sürece pozisyonu açık tutup kârı "takip ederek"
        korumayı sağlar. None ile kapatılabilir.
    """
    commission = commission_bps / 10_000.0
    capital = initial_capital
    equity = []
    trades: list[Trade] = []
    has_atr = "atr" in df.columns

    position = None  # Trade objesi ya da None
    buy_labels = {"AL", "GÜÇLÜ AL"}
    sell_labels = {"SAT", "GÜÇLÜ SAT"}

    for ts, row in df.iterrows():
        price = row["close"]
        sig = row["signal"]
        atr_val = row["atr"] if has_atr else None

        # Pozisyon varsa: en iyi fiyatı (extreme) güncelle ve stop/hedef kontrolü yap
        if position is not None:
            if position.direction == "long":
                position.extreme_price = max(position.extreme_price, price)
            else:
                position.extreme_price = min(position.extreme_price, price)

            change = (price / position.entry_price - 1) if position.direction == "long" \
                else (position.entry_price / price - 1)

            exit_reason = None
            if stop_loss_pct and change <= -stop_loss_pct:
                exit_reason = "stop_loss"
            elif take_profit_pct and change >= take_profit_pct:
                exit_reason = "take_profit"
            elif trailing_atr_mult and atr_val and not pd.isna(atr_val):
                if position.direction == "long":
                    trail_stop = position.extreme_price - trailing_atr_mult * atr_val
                    if price <= trail_stop:
                        exit_reason = "trailing_stop"
                else:
                    trail_stop = position.extreme_price + trailing_atr_mult * atr_val
                    if price >= trail_stop:
                        exit_reason = "trailing_stop"

            if exit_reason:
                exit_price = price * (1 - commission) if position.direction == "long" else price * (1 + commission)
                position.exit_time, position.exit_price, position.reason = ts, exit_price, exit_reason
                capital *= (1 + position.pnl_pct)
                trades.append(position)
                position = None

        # Sinyale göre giriş / çıkış
        if position is None:
            if sig in buy_labels:
                entry_price = price * (1 + commission)
                position = Trade(entry_time=ts, entry_price=entry_price, direction="long",
                                  extreme_price=entry_price)
            elif allow_short and sig in sell_labels:
                entry_price = price * (1 - commission)
                position = Trade(entry_time=ts, entry_price=entry_price, direction="short",
                                  extreme_price=entry_price)
        else:
            if position.direction == "long" and sig in sell_labels:
                exit_price = price * (1 - commission)
                position.exit_time, position.exit_price, position.reason = ts, exit_price, "signal"
                capital *= (1 + position.pnl_pct)
                trades.append(position)
                position = None
                if allow_short and sig in sell_labels:
                    entry_price = price * (1 - commission)
                    position = Trade(entry_time=ts, entry_price=entry_price, direction="short",
                                      extreme_price=entry_price)
            elif position.direction == "short" and sig in buy_labels:
                exit_price = price * (1 + commission)
                position.exit_time, position.exit_price, position.reason = ts, exit_price, "signal"
                capital *= (1 + position.pnl_pct)
                trades.append(position)
                position = None

        # Açık pozisyonun mark-to-market değeriyle equity güncelle
        if position is not None:
            unreal = (price / position.entry_price - 1) if position.direction == "long" \
                else (position.entry_price / price - 1)
            equity.append(capital * (1 + unreal))
        else:
            equity.append(capital)

    # Dönem sonunda açık pozisyon varsa kapat
    if position is not None:
        last_price = df["close"].iloc[-1]
        exit_price = last_price * (1 - commission if position.direction == "long" else -commission)
        position.exit_time = df.index[-1]
        position.exit_price = exit_price
        position.reason = "period_end"
        capital *= (1 + position.pnl_pct)
        trades.append(position)

    equity_curve = pd.Series(equity, index=df.index, name="equity")
    metrics = _compute_metrics(trades, equity_curve, initial_capital, df)
    return BacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)


def _compute_metrics(trades: list[Trade], equity: pd.Series, initial_capital: float, df: pd.DataFrame) -> dict:
    if len(equity) == 0:
        return {}

    total_return = equity.iloc[-1] / initial_capital - 1
    closed = [t for t in trades if t.pnl_pct is not None]
    wins = [t for t in closed if t.pnl_pct > 0]
    losses = [t for t in closed if t.pnl_pct <= 0]

    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0.0
    gross_profit = sum(t.pnl_pct for t in wins)
    gross_loss = abs(sum(t.pnl_pct for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = drawdown.min()

    returns = equity.pct_change().dropna()
    periods_per_year = _infer_periods_per_year(df.index)
    if returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)
    else:
        sharpe = 0.0

    buy_hold_return = df["close"].iloc[-1] / df["close"].iloc[0] - 1

    return {
        "total_return_pct": round(total_return * 100, 2),
        "buy_hold_return_pct": round(buy_hold_return * 100, 2),
        "num_trades": len(closed),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win * 100, 2),
        "avg_loss_pct": round(avg_loss * 100, 2),
        "profit_factor": round(profit_factor, 2) if np.isfinite(profit_factor) else "inf",
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "sharpe_ratio_annualized": round(float(sharpe), 2),
        "final_equity": round(float(equity.iloc[-1]), 2),
    }


def _infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 252
    delta = (index[1] - index[0]).total_seconds()
    if delta <= 0:
        return 252
    seconds_per_year = 365 * 24 * 3600
    return max(seconds_per_year / delta, 1)

"""Shared outcome rules — one definition of win, loss, breakeven, win rate.

Every surface that reports an outcome reads these helpers: the analytics
API, the Telegram bot, and the weekend-review prompt. A number must never
mean two different things on two screens.

Breakeven band
--------------
A trade that nets within $5 of zero is a scratch — commission and slippage
dust, a position closed by hand at scratch. It is neither a win nor a loss.

Win-rate denominator
--------------------
``wins / (wins + losses)`` — the *decided* trades.

Scratch trades are excluded on purpose. The breakeven band exists to keep
them out of the win/loss decision; dividing by every closed trade would
re-include them and make a scratch cost as much as a real loss, which
understates the rate and defeats the band. The breakeven count is always
reported alongside the rate so the number stays explainable.

This module is pure — no I/O, no database, no framework imports — so it can
be imported from routers, services and tests alike.
"""

from __future__ import annotations

from typing import Iterable

# A trade netting within ±$5 of zero counts as breakeven, not a win or loss.
BE_TOLERANCE = 5.0


def is_win(net: float) -> bool:
    """True when the trade netted more than the breakeven band."""
    return net > BE_TOLERANCE


def is_loss(net: float) -> bool:
    """True when the trade netted less than minus the breakeven band."""
    return net < -BE_TOLERANCE


def is_breakeven(net: float) -> bool:
    """True when the trade landed inside the breakeven band."""
    return abs(net) <= BE_TOLERANCE


def sign(net: float) -> int:
    """Outcome as 1 (win), -1 (loss) or 0 (breakeven)."""
    if is_win(net):
        return 1
    if is_loss(net):
        return -1
    return 0


def win_loss_counts(nets: Iterable[float]) -> tuple[int, int, int]:
    """Split net results into (wins, losses, breakeven)."""
    wins = losses = be = 0
    for net in nets:
        if is_win(net):
            wins += 1
        elif is_loss(net):
            losses += 1
        else:
            be += 1
    return wins, losses, be


def win_rate(wins: int, losses: int) -> float:
    """Win rate over decided trades: wins / (wins + losses), as a percent.

    Returns 0.0 when nothing was decided (no wins and no losses), which is
    the honest answer for an empty or all-scratch sample.
    """
    decided = wins + losses
    return round(wins / decided * 100, 2) if decided else 0.0


def win_rate_of(nets: Iterable[float]) -> float:
    """Win rate for a collection of net results."""
    wins, losses, _be = win_loss_counts(nets)
    return win_rate(wins, losses)

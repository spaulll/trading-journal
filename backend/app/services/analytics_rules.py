"""Shared outcome rules — one definition of win, loss, breakeven, win rate.

Every surface that reports an outcome reads these helpers: the analytics
API, the Telegram bot, and the weekend-review prompt. A number must never
mean two different things on two screens.

Breakeven band
--------------
A trade that nets within $5 of zero is a scratch — commission and slippage
dust, a position closed by hand at scratch. It is neither a win nor a loss.

Unpriced trades
---------------
A trade with no net P&L is *unpriced*, not a scratch. The symbol had no
contract, so the dollar outcome is unknown — it might have been a $2
scratch or a $200 win. Scoring it as breakeven would quietly drag the win
rate down and break a win streak over a trade that was never priced, so
unpriced trades are counted separately and excluded from every outcome
decision.

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

from dataclasses import dataclass
from typing import Iterable, Optional

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
    """Split net results into (wins, losses, breakeven).

    Only for results that are known. Use :func:`split_outcomes` when a
    trade may be unpriced.
    """
    wins = losses = be = 0
    for net in nets:
        if is_win(net):
            wins += 1
        elif is_loss(net):
            losses += 1
        else:
            be += 1
    return wins, losses, be


@dataclass(frozen=True)
class OutcomeCounts:
    """The four ways a closed trade can end.

    ``unpriced`` is a trade with no net P&L — the outcome is unknown, so
    it takes part in no decision.
    """

    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    unpriced: int = 0

    @property
    def decided(self) -> int:
        """The trades whose outcome is known and not a scratch."""
        return self.wins + self.losses

    @property
    def priced(self) -> int:
        """The trades with a known net — every outcome bucket but unpriced."""
        return self.wins + self.losses + self.breakeven


def split_outcomes(nets: Iterable[Optional[float]]) -> OutcomeCounts:
    """Split net results into wins, losses, scratches and unpriced trades.

    A ``None`` net means the trade was never priced. It is counted as
    unpriced and left out of the win/loss/scratch decision, so it can
    neither drag the win rate down nor break a streak.
    """
    wins = losses = be = unpriced = 0
    for net in nets:
        if net is None:
            unpriced += 1
        elif is_win(net):
            wins += 1
        elif is_loss(net):
            losses += 1
        else:
            be += 1
    return OutcomeCounts(wins, losses, be, unpriced)


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

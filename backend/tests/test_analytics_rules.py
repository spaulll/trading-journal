"""Tests for the shared outcome rules.

The breakeven band and the win-rate denominator used to be defined in
several places, and the API and the dashboard disagreed about the
denominator. These lock the single definition down.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.database import engine
from app.models import Trade
from app.services.analytics_rules import (
    BE_TOLERANCE,
    is_breakeven,
    is_loss,
    is_win,
    sign,
    win_loss_counts,
    win_rate,
    win_rate_of,
)


def test_breakeven_band_edges():
    assert BE_TOLERANCE == 5.0
    assert is_win(5.01)
    assert not is_win(5.0)
    assert is_loss(-5.01)
    assert not is_loss(-5.0)
    assert is_breakeven(5.0)
    assert is_breakeven(-5.0)
    assert is_breakeven(0.0)


def test_sign_maps_the_outcome():
    assert sign(200) == 1
    assert sign(-200) == -1
    assert sign(3) == 0


def test_win_loss_counts_splits_the_three_outcomes():
    assert win_loss_counts([200, -200, 3, 0, -1, 400]) == (2, 1, 3)
    assert win_loss_counts([]) == (0, 0, 0)


def test_win_rate_uses_decided_trades_only():
    """Scratch trades must not drag the rate down like a real loss."""
    assert win_rate(3, 1) == 75.0
    assert win_rate(0, 0) == 0.0
    assert win_rate_of([300, 200, 100, -250, 2, -3]) == 75.0


def test_api_and_dashboard_agree_on_the_win_rate(client):
    """The API rate and the client-side rate must be the same number."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    nets = [300.0, 200.0, 100.0, -250.0, 2.0, -3.0]  # 3W 1L 2BE
    with Session(engine) as session:
        for i, net in enumerate(nets):
            session.add(
                Trade(
                    ticket=f"RATE-{i}",
                    symbol="GOLD",
                    direction="buy",
                    size=0.1,
                    entry_price=4000.0,
                    initial_sl=3990.0,
                    exit_price=4010.0,
                    timestamp_open=now - timedelta(hours=10),
                    timestamp_close=now - timedelta(hours=9),
                    net_pnl=net,
                    gross_pnl=net,
                    status="CLOSED",
                    r_multiple=1.0,
                )
            )
        session.commit()

    summary = client.get("/api/analytics/summary").json()
    assert summary["wins"] == 3
    assert summary["losses"] == 1
    assert summary["breakeven"] == 2
    assert summary["win_rate"] == 75.0

    kpi = client.get("/api/analytics/kpi-dashboard").json()["win_rate"]
    assert kpi["rate"] == 75.0
    assert kpi["breakeven"] == 2

    long_short = client.get("/api/analytics/long-short-stats").json()
    assert long_short["buy"]["win_rate"] == 75.0
    assert long_short["all"]["win_rate"] == 75.0

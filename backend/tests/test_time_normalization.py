"""Every write path stores naive UTC — including the two that did not.

A naive datetime is already UTC by policy. An aware one carries its own
instant, and storing it as wall clock loses that: ``10:00+05:30`` became
``10:00`` instead of ``04:30``, which can move a trade into the wrong
trading day (and therefore the wrong daily P&L).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from app.models import Trade


def _record(**overrides) -> dict:
    payload = {
        "symbol": "GOLD",
        "direction": "buy",
        "size": 0.1,
        "entry_price": 4000.0,
        "exit_price": 4015.0,
        "initial_sl": 3990.0,
        "entry_time": "2026-10-06T10:00:00",
        "exit_time": "2026-10-06T10:45:00",
        "gross_pnl": 15.0,
    }
    payload.update(overrides)
    return payload


def _stored(session, ticket: str) -> Trade:
    return session.exec(select(Trade).where(Trade.ticket == ticket)).one()


def test_a_backfill_with_an_offset_keeps_its_instant(client, session):
    response = client.post(
        "/api/trades/backfill",
        json=_record(
            ticket="OFFSET-1",
            entry_time="2026-10-06T10:00:00+05:30",
            exit_time="2026-10-06T10:45:00+05:30",
        ),
    )
    assert response.status_code == 200, response.text

    trade = _stored(session, "OFFSET-1")
    assert trade.timestamp_open == datetime(2026, 10, 6, 4, 30)
    assert trade.entry_time == datetime(2026, 10, 6, 4, 30)
    assert trade.timestamp_close == datetime(2026, 10, 6, 5, 15)


def test_a_backfill_with_z_keeps_its_instant(client, session):
    response = client.post(
        "/api/trades/backfill",
        json=_record(
            ticket="ZULU-1",
            entry_time="2026-10-06T10:00:00Z",
            exit_time="2026-10-06T10:45:00Z",
        ),
    )
    assert response.status_code == 200, response.text
    assert _stored(session, "ZULU-1").timestamp_open == datetime(2026, 10, 6, 10, 0)


def test_a_naive_backfill_is_left_alone(client, session):
    response = client.post("/api/trades/backfill", json=_record(ticket="NAIVE-1"))
    assert response.status_code == 200, response.text
    assert _stored(session, "NAIVE-1").timestamp_open == datetime(2026, 10, 6, 10, 0)


def test_a_patch_normalises_an_aware_entry(client, session):
    opened = client.post(
        "/api/trades/open",
        json={
            "symbol": "GOLD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 4000.0,
            "initial_sl": 3990.0,
            "ticket": "PATCH-1",
        },
    ).json()

    response = client.patch(
        f"/api/trades/{opened['id']}",
        json={"timestamp_open": "2026-10-06T10:00:00+05:30"},
    )
    assert response.status_code == 200, response.text

    trade = _stored(session, "PATCH-1")
    assert trade.timestamp_open == datetime(2026, 10, 6, 4, 30)
    # The mirrored pair moves with it.
    assert trade.entry_time == datetime(2026, 10, 6, 4, 30)


def test_a_patch_normalises_an_aware_exit(client, session):
    opened = client.post(
        "/api/trades/open",
        json={
            "symbol": "GOLD",
            "direction": "buy",
            "size": 0.1,
            "entry_price": 4000.0,
            "initial_sl": 3990.0,
            "ticket": "PATCH-2",
        },
    ).json()

    response = client.patch(
        f"/api/trades/{opened['id']}",
        json={"exit_time": "2026-10-06T21:00:00Z", "exit_price": 4010.0},
    )
    assert response.status_code == 200, response.text

    trade = _stored(session, "PATCH-2")
    assert trade.exit_time == datetime(2026, 10, 6, 21, 0)
    assert trade.timestamp_close == datetime(2026, 10, 6, 21, 0)

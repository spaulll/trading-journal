"""The broker clock: a rule with a date, not a single offset.

A single integer is correct until the first daylight-saving switch and wrong
forever after. These tests pin the two properties that fix that:

  - the offset is resolved from the *moment's own date*, so a backfilled
    trade is translated with the offset that was in force back then;
  - a manual correction pins from its date onward, and the automatic rule
    resumes only when every correction is cleared.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.models import Account, AppSetting
from app.services import broker_clock
from app.services.broker_clock import BrokerClock, format_label


def _clock(**kwargs) -> BrokerClock:
    return BrokerClock(**kwargs)


# --- the automatic rule ----------------------------------------------------


def test_us_rule_runs_three_hours_ahead_in_summer_and_two_in_winter():
    clock = _clock(base_offset_minutes=120, dst="us")
    assert clock.offset_for(datetime(2026, 10, 30, 16, 0)) == 180
    assert clock.offset_for(datetime(2026, 11, 2, 16, 0)) == 120
    assert clock.offset_for(datetime(2027, 1, 15, 16, 0)) == 120
    assert clock.offset_for(datetime(2027, 6, 15, 16, 0)) == 180


def test_eu_rule_moves_on_the_eu_calendar():
    clock = _clock(base_offset_minutes=120, dst="eu")
    # EU summer time ends on the last Sunday of October.
    assert clock.offset_for(datetime(2026, 10, 24, 16, 0)) == 180
    assert clock.offset_for(datetime(2026, 10, 26, 16, 0)) == 120


def test_a_fixed_clock_never_moves():
    clock = _clock(base_offset_minutes=180, dst="none")
    assert clock.offset_for(datetime(2026, 1, 1)) == 180
    assert clock.offset_for(datetime(2030, 7, 1)) == 180
    assert clock.next_change(datetime(2026, 10, 30, 16, 0)) is None


def test_the_next_change_is_the_real_switch_not_the_next_midnight():
    clock = _clock(base_offset_minutes=120, dst="us")
    upcoming = clock.next_change(datetime(2026, 10, 30, 16, 0))
    assert upcoming is not None
    when, minutes = upcoming
    # 02:00 New York on the first Sunday of November is 06:00 UTC.
    assert when == datetime(2026, 11, 1, 6, 0)
    assert minutes == 120
    assert format_label(minutes) == "UTC+2:00"


def test_an_override_pins_from_its_own_date():
    clock = _clock(
        base_offset_minutes=120,
        dst="us",
        overrides=((datetime(2026, 11, 1, 6, 0), 180),),
    )
    assert clock.offset_for(datetime(2026, 10, 15, 12, 0)) == 180  # rule: summer
    assert clock.offset_for(datetime(2026, 11, 2, 12, 0)) == 180  # pinned
    assert clock.offset_for(datetime(2027, 6, 1, 12, 0)) == 180  # still pinned
    assert clock.is_manual_at(datetime(2026, 11, 2, 12, 0)) is True
    assert clock.is_manual_at(datetime(2026, 10, 15, 12, 0)) is False


def test_an_override_cannot_be_aware():
    with pytest.raises(ValueError):
        _clock(
            overrides=((datetime(2026, 11, 1, tzinfo=timezone.utc), 180),),
        )


def test_an_unknown_dst_rule_is_refused():
    with pytest.raises(ValueError):
        _clock(dst="mars")


# --- storage and firm resolution -------------------------------------------


def test_a_clock_is_stored_per_firm_and_resolved_through_the_account(session):
    account = Account(alias="gft-5k-p2", firm="GFT")
    other = Account(alias="ftmo-100k", firm="FTMO")
    session.add(account)
    session.add(other)
    session.commit()
    session.refresh(account)
    session.refresh(other)

    broker_clock.set_clock(session, "GFT", 120, "us")
    broker_clock.set_clock(session, "FTMO", 180, "none")
    session.commit()

    gft = broker_clock.get_clock_for_account(session, account.id)
    ftmo = broker_clock.get_clock_for_account(session, other.id)
    assert gft is not None and gft.base_offset_minutes == 120 and gft.dst == "us"
    assert ftmo is not None and ftmo.base_offset_minutes == 180 and ftmo.dst == "none"


def test_an_account_without_a_firm_falls_back_to_the_default(session):
    account = Account(alias="solo", firm="")
    session.add(account)
    session.commit()
    session.refresh(account)

    broker_clock.set_clock(session, None, 150, "none")
    session.commit()

    clock = broker_clock.get_clock_for_account(session, account.id)
    assert clock is not None and clock.base_offset_minutes == 150


def test_the_legacy_single_offset_is_still_read(session):
    session.add(AppSetting(key=broker_clock.LEGACY_OFFSET_KEY, value="180"))
    session.commit()

    clock = broker_clock.get_clock(session)
    assert clock is not None
    assert clock.base_offset_minutes == 180
    assert clock.dst == "none"
    assert broker_clock.get_offset_minutes(session) == 180


def test_editing_the_rule_keeps_manual_corrections(session):
    broker_clock.set_clock(session, "GFT", 120, "none")
    broker_clock.set_override(session, "GFT", 180, datetime(2026, 11, 1, 6, 0))
    session.commit()

    clock = broker_clock.set_clock(session, "GFT", 120, "us")
    session.commit()

    assert len(clock.overrides) == 1
    assert clock.dst == "us"


def test_clearing_corrections_restores_the_rule(session):
    broker_clock.set_clock(session, "GFT", 120, "us")
    broker_clock.set_override(session, "GFT", 180, datetime(2026, 11, 1, 6, 0))
    session.commit()

    clock = broker_clock.clear_overrides(session, "GFT")
    session.commit()

    assert clock.overrides == ()
    assert clock.offset_for(datetime(2026, 11, 2, 12, 0)) == 120


# --- the HTTP surface ------------------------------------------------------


def _put(client, **payload):
    body = {"firm": "GFT", "base_offset_minutes": 120, "dst": "us"}
    body.update(payload)
    return client.put("/api/settings/broker-clock", json=body)


def test_the_api_returns_the_resolved_clock_and_its_next_change(client):
    response = _put(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["firm"] == "GFT"
    assert body["base_offset_minutes"] == 120
    assert body["dst"] == "us"
    assert body["label"] is not None

    listed = client.get("/api/settings/broker-clock")
    assert listed.status_code == 200
    clocks = listed.json()["clocks"]
    assert any(clock["firm"] == "GFT" and clock["configured"] for clock in clocks)


def test_the_api_rejects_an_unknown_dst_rule(client):
    assert _put(client, dst="lunar").status_code == 422


def test_the_api_rejects_an_implausible_offset(client):
    assert _put(client, base_offset_minutes=5000).status_code == 422


def test_an_override_can_be_recorded_and_cleared_over_http(client):
    assert _put(client).status_code == 200

    pinned = client.post(
        "/api/settings/broker-clock/override",
        json={
            "firm": "GFT",
            "offset_minutes": 180,
            "effective_from": "2026-10-01T00:00:00",
        },
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["manual"] is True
    assert len(pinned.json()["overrides"]) == 1

    cleared = client.delete("/api/settings/broker-clock/override", params={"firm": "GFT"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["overrides"] == []


def test_the_legacy_offset_endpoint_still_answers(client):
    _put(client, base_offset_minutes=180, dst="none")
    response = client.get("/api/settings/broker-offset")
    assert response.status_code == 200
    body = response.json()
    assert body["offset_minutes"] == 180
    assert body["label"] == "UTC+3:00"

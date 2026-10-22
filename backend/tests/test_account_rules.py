"""Prop-challenge rules: configured limits, live readings, milestones.

Phase 9 turns the account limits into trackable rules. These tests pin the
semantics that make the card trustworthy:

  - a zero limit is not configured, so it never becomes a rule;
  - a rule's ``met_at`` is a milestone and is not overwritten;
  - a daily-loss breach belongs to its trading day and resets on the next;
  - clearing a limit removes the rule instead of leaving a stale row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models import AccountEvent, AccountRule, Trade


def _account(client, **overrides) -> dict:
    payload = {
        "alias": "prop-eval",
        "firm": "FTMO",
        "start_balance": 100_000.0,
        "base_currency": "USD",
    }
    payload.update(overrides)
    response = client.post("/api/accounts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _trade(
    client,
    account_id: int,
    ticket: str,
    day: str,
    gross_pnl: float,
    *,
    at: str | None = None,
) -> dict:
    timestamp = at or f"{day}T10:00:00"
    payload = {
        "account_id": account_id,
        "ticket": ticket,
        "symbol": "GOLD",
        "direction": "buy",
        "size": 0.1,
        "entry_price": 4000.0,
        "exit_price": 4010.0,
        "entry_time": timestamp,
        "exit_time": timestamp,
        "gross_pnl": gross_pnl,
    }
    response = client.post("/api/trades/backfill", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _rules(client, account_id: int) -> dict[str, dict]:
    response = client.get(f"/api/accounts/{account_id}/rules")
    assert response.status_code == 200, response.text
    return {rule["kind"]: rule for rule in response.json()}


def test_rules_track_the_configured_limits(client):
    account = _account(
        client,
        profit_target_pct=10.0,
        max_loss_pct=10.0,
        daily_loss_pct=5.0,
        min_trading_days=5,
        consistency_pct=40.0,
    )
    _trade(client, account["id"], "RULE-1", "2026-09-20", 3000.0)
    _trade(client, account["id"], "RULE-2", "2026-09-21", 2000.0)

    rules = _rules(client, account["id"])
    assert list(rules) == [
        "profit_target",
        "max_loss",
        "daily_loss",
        "min_days",
        "consistency",
    ]

    target = rules["profit_target"]
    assert target["current"] == 5.0
    assert target["target"] == 10.0
    assert target["status"] == "pending"
    assert target["unit"] == "%"

    days = rules["min_days"]
    assert days["current"] == 2.0
    assert days["target"] == 5.0
    assert days["unit"] == "days"
    assert days["status"] == "pending"

    # 3,000 of the 5,000 profit came from one day: over the 40% limit.
    consistency = rules["consistency"]
    assert consistency["current"] == 60.0
    assert consistency["status"] == "pending"
    assert "limit is 40.00%" in consistency["warning"]

    assert rules["max_loss"]["current"] == 0.0
    assert rules["daily_loss"]["current"] == 0.0
    assert rules["max_loss"]["status"] == "pending"
    assert rules["daily_loss"]["status"] == "pending"


def test_an_account_reports_its_days_traded(client):
    account = _account(client)
    _trade(client, account["id"], "DAY-1", "2026-09-20", 100.0)
    _trade(client, account["id"], "DAY-1B", "2026-09-20", 50.0)
    _trade(client, account["id"], "DAY-2", "2026-09-21", 75.0)

    read = client.get(f"/api/accounts/{account['id']}").json()
    assert read["days_traded"] == 2
    assert read["min_trading_days"] == 0
    assert read["total_trades"] == 3


def test_a_passed_target_keeps_its_timestamp(client):
    account = _account(client, profit_target_pct=5.0)
    _trade(client, account["id"], "TARGET-1", "2026-09-20", 5000.0)

    first = _rules(client, account["id"])["profit_target"]
    assert first["status"] == "met"
    assert first["met_at"] is not None

    # Give part of the profit back. The rule was satisfied; history does
    # not get rewritten.
    _trade(client, account["id"], "TARGET-2", "2026-09-21", -1000.0)
    second = _rules(client, account["id"])["profit_target"]
    assert second["current"] == 4.0
    assert second["status"] == "met"
    assert second["met_at"] == first["met_at"]


def test_a_daily_loss_breach_resets_on_the_next_trading_day(client, session):
    account = _account(client, daily_loss_pct=2.0)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stamp = now.isoformat(timespec="seconds")
    _trade(client, account["id"], "DAILY-1", "", -3000.0, at=stamp)

    breached = _rules(client, account["id"])["daily_loss"]
    assert breached["status"] == "breached"
    assert breached["current"] == 3.0

    # Move both the breach and the losing trade back one day: the current
    # trading day is clean, so the rule must not stay breached forever.
    yesterday = now - timedelta(days=1)
    trade = session.exec(select(Trade).where(Trade.ticket == "DAILY-1")).one()
    trade.timestamp_open = yesterday
    trade.timestamp_close = yesterday
    trade.entry_time = yesterday
    trade.exit_time = yesterday
    session.add(trade)
    row = session.exec(
        select(AccountRule).where(
            AccountRule.account_id == account["id"],
            AccountRule.kind == "daily_loss",
        )
    ).one()
    row.met_at = yesterday
    session.add(row)
    session.commit()

    reset = _rules(client, account["id"])["daily_loss"]
    assert reset["status"] == "pending"
    assert reset["current"] == 0.0
    # The old breach stays in the event log.
    events = session.exec(
        select(AccountEvent).where(
            AccountEvent.account_id == account["id"],
            AccountEvent.kind == "rule_breached",
        )
    ).all()
    assert len(events) == 1


def test_resolving_a_rule_is_logged_once(client, session):
    account = _account(client, profit_target_pct=5.0)
    _trade(client, account["id"], "EVENT-1", "2026-09-20", 5000.0)

    _rules(client, account["id"])
    _rules(client, account["id"])
    events = session.exec(
        select(AccountEvent).where(
            AccountEvent.account_id == account["id"],
            AccountEvent.kind == "rule_met",
        )
    ).all()
    assert len(events) == 1
    assert '"rule": "profit_target"' in events[0].payload


def test_clearing_a_limit_removes_its_rule(client):
    account = _account(
        client,
        profit_target_pct=10.0,
        min_trading_days=20,
        consistency_pct=40.0,
    )
    assert set(_rules(client, account["id"])) == {
        "profit_target",
        "min_days",
        "consistency",
    }

    response = client.patch(
        f"/api/accounts/{account['id']}",
        json={
            "profit_target_pct": None,
            "min_trading_days": 0,
            "consistency_pct": None,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["profit_target_pct"] is None
    assert response.json()["consistency_pct"] is None
    assert response.json()["min_trading_days"] == 0
    assert _rules(client, account["id"]) == {}


def test_an_empty_account_has_no_rules(client):
    account = _account(client)
    assert _rules(client, account["id"]) == {}


def test_check_validates_the_rule_kind(client):
    account = _account(client, min_trading_days=5)
    response = client.post(f"/api/accounts/{account['id']}/rules/not-a-rule/check")
    assert response.status_code == 422
    response = client.post(f"/api/accounts/{account['id']}/rules/max_loss/check")
    assert response.status_code == 404

    checked = client.post(f"/api/accounts/{account['id']}/rules/min_days/check")
    assert checked.status_code == 200, checked.text
    assert checked.json()["kind"] == "min_days"


def test_the_timeline_is_anchored_by_the_account_creation(client):
    account = _account(client)

    response = client.get(f"/api/accounts/{account['id']}/timeline")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    created = body[0]
    assert created["kind"] == "account_created"
    assert created["label"] == "Account created"
    assert created["payload"] == {"alias": "prop-eval"}
    assert created["id"] is None


def test_the_timeline_records_rule_and_status_changes(client):
    account = _account(client, profit_target_pct=5.0)
    _trade(client, account["id"], "TIMELINE-1", "2026-09-20", 5000.0)
    _rules(client, account["id"])

    patched = client.patch(
        f"/api/accounts/{account['id']}", json={"status": "passed"}
    )
    assert patched.status_code == 200, patched.text

    body = client.get(f"/api/accounts/{account['id']}/timeline").json()
    assert [event["kind"] for event in body] == [
        "status_changed",
        "rule_met",
        "account_created",
    ]
    assert body[0]["label"] == "Status: active → passed"
    assert body[0]["payload"] == {"from": "active", "to": "passed"}
    assert body[1]["label"] == "Profit target met"
    assert body[1]["payload"]["rule"] == "profit_target"
    assert body[1]["payload"]["target"] == 5.0


def test_an_unchanged_status_does_not_add_a_timeline_event(client):
    account = _account(client)
    client.patch(f"/api/accounts/{account['id']}", json={"status": "active"})

    body = client.get(f"/api/accounts/{account['id']}/timeline").json()
    assert [event["kind"] for event in body] == ["account_created"]


def test_the_timeline_limit_keeps_the_creation_anchor(client):
    account = _account(client)
    for status in ("passed", "active", "breached"):
        client.patch(f"/api/accounts/{account['id']}", json={"status": status})

    body = client.get(
        f"/api/accounts/{account['id']}/timeline", params={"limit": 2}
    ).json()
    assert [event["kind"] for event in body] == [
        "status_changed",
        "status_changed",
        "account_created",
    ]


def test_the_days_rule_warns_when_the_deadline_is_too_close(client):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        min_trading_days=10,
        deadline=(today + timedelta(days=2)).isoformat(),
    )
    _trade(
        client,
        account["id"],
        "WARN-1",
        (today - timedelta(days=3)).isoformat(),
        100.0,
    )

    rule = _rules(client, account["id"])["min_days"]
    assert rule["status"] == "pending"
    assert rule["warning"] is not None
    assert "At risk" in rule["warning"]
    assert "9 more trading days needed" in rule["warning"]
    assert "weekdays left" in rule["warning"]
    assert rule["days_left"] is not None and rule["days_left"] <= 2


def test_a_deadline_that_passed_marks_the_days_rule_missed(client):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        min_trading_days=10,
        deadline=(today - timedelta(days=1)).isoformat(),
    )

    rule = _rules(client, account["id"])["min_days"]
    assert rule["status"] == "missed"
    assert rule["warning"] == "Deadline passed with 0 of 10 trading days."
    assert rule["days_left"] is not None and rule["days_left"] < 0


def test_enough_time_left_does_not_warn(client):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        min_trading_days=2,
        deadline=(today + timedelta(days=30)).isoformat(),
    )

    rule = _rules(client, account["id"])["min_days"]
    assert rule["status"] == "pending"
    assert rule["warning"] is None


def test_meeting_the_days_requirement_clears_the_warning(client):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        min_trading_days=1,
        deadline=(today + timedelta(days=2)).isoformat(),
    )
    _trade(client, account["id"], "WARN-MET", today.isoformat(), 100.0)

    rule = _rules(client, account["id"])["min_days"]
    assert rule["status"] == "met"
    assert rule["met_at"] is not None
    assert rule["warning"] is None


def test_the_telegram_detail_shows_every_rule(client, session):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        profit_target_pct=5.0,
        max_loss_pct=10.0,
        daily_loss_pct=5.0,
        min_trading_days=10,
        consistency_pct=40.0,
        deadline=(today + timedelta(days=2)).isoformat(),
    )
    _trade(client, account["id"], "TG-1", (today - timedelta(days=2)).isoformat(), 3000.0)
    _trade(client, account["id"], "TG-2", (today - timedelta(days=1)).isoformat(), 2000.0)
    _trade(client, account["id"], "TG-3", today.isoformat(), 1000.0)

    from app.services.telegram_bot import account_detail_content

    rendered = account_detail_content(session, account["id"])
    assert rendered is not None
    text, keyboard = rendered

    assert "🏦 <b>@prop-eval</b>" in text
    assert "🎯 Profit target" in text
    assert "6% / 5%" in text
    assert "✅ met" in text
    from app.services.broker_clock import IST_OFFSET

    web = {
        rule["kind"]: rule
        for rule in client.get(f"/api/accounts/{account['id']}/rules").json()
    }
    met_at = datetime.fromisoformat(web["profit_target"]["met_at"])
    assert f"· {(met_at + IST_OFFSET).strftime('%d %b')}" in text
    assert "🛡️ Max loss" in text
    assert "0% / 10%" in text
    assert "📉 Daily loss" in text
    assert "0% today / 5%" in text
    assert "📅 Trading days" in text
    assert "3 / 10 days" in text
    assert "⚖️ Consistency" in text
    assert "50% ≤ 40%" in text
    assert "At risk:" in text
    assert "📊 Trades  0 open · 3 total" in text
    assert keyboard is not None


def test_the_telegram_accounts_page_shows_days_progress(client, session):
    today = datetime.now(timezone.utc).date()
    account = _account(
        client,
        min_trading_days=10,
        deadline=(today + timedelta(days=2)).isoformat(),
    )
    _trade(
        client,
        account["id"],
        "TG-LIST",
        (today - timedelta(days=1)).isoformat(),
        100.0,
    )

    from app.services.telegram_bot import accounts_page_content

    rendered = accounts_page_content(session, 0)
    assert rendered is not None
    text, keyboard = rendered

    assert "📅 1/10d ⚠️" in text
    assert keyboard is not None


def test_a_telegram_account_without_rules_has_no_rule_block(client, session):
    account = _account(client)

    from app.services.telegram_bot import account_detail_content

    rendered = account_detail_content(session, account["id"])
    assert rendered is not None
    text, _ = rendered
    assert "Profit target" not in text
    assert text.count("━━━━━━━━━━━━") == 1

"""Tests for the analytics-depth aggregations (Phase 7).

Every new endpoint is a second definition of a number the dashboard already
reports, so the tests pin the shared rules on it too: the $5 breakeven band,
the decided-trade win-rate denominator, USD as the only summing currency,
and unpriced trades as unknown rather than zero.

The small-sample rule is the other half: a setup below ``MIN_SAMPLE_SIZE``
must come back flagged as insufficient, not as a winner on noise.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlmodel import Session

from app.database import engine
from app.models import Account, Tag, Trade
from app.services.analytics_stats import (
    drawdown_curve,
    mean_confidence,
    min_sample_size,
    ruin_probability,
)

BASE = datetime(2026, 9, 1, 10, 0)


def _at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def _closed(
    ticket: str,
    net: float | None,
    *,
    minutes: int = 0,
    symbol: str = "EURUSD",
    account_id: int | None = None,
    tags: list[Tag] | None = None,
    realized_risk: float | None = None,
    initial_risk: float | None = None,
    r: float | None = None,
) -> Trade:
    """A CLOSED trade with an explicit net, ready for the session."""
    when = _at(minutes)
    return Trade(
        ticket=ticket,
        symbol=symbol,
        direction="buy",
        size=0.1,
        entry_price=1.0,
        initial_sl=0.9,
        exit_price=1.1,
        timestamp_open=when,
        timestamp_close=when,
        net_pnl=net,
        gross_pnl=net,
        r_multiple=r,
        realized_risk=realized_risk,
        initial_risk=initial_risk,
        risk_unit="USD" if (realized_risk or initial_risk) else None,
        status="CLOSED",
        account_id=account_id,
        tags=tags or [],
    )


def _store(trades: list[Trade], session: Session | None = None) -> None:
    """Persist trades, reusing the caller's session when tags are attached."""
    if session is not None:
        for trade in trades:
            session.add(trade)
        session.commit()
        return
    with Session(engine) as own:
        for trade in trades:
            own.add(trade)
        own.commit()


def _tag(session: Session, name: str, category: str = "setup") -> Tag:
    tag = Tag(name=name, category=category)
    session.add(tag)
    session.commit()
    session.refresh(tag)
    return tag


def _account(session: Session, alias: str, balance: float, firm: str = "Test") -> Account:
    account = Account(firm=firm, alias=alias, start_balance=balance, base_currency="USD")
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


# --- per-symbol performance -------------------------------------------------


def test_symbol_performance_groups_by_symbol(client):
    _store(
        [
            _closed("SP-1", 100.0, minutes=1),
            _closed("SP-2", -50.0, minutes=2),
            _closed("SP-3", 3.0, minutes=3, symbol="GOLD"),
        ]
    )

    body = client.get("/api/analytics/symbol-performance").json()
    rows = {row["symbol"]: row for row in body["symbols"]}

    assert rows["EURUSD"]["trade_count"] == 2
    assert rows["EURUSD"]["net_pnl"] == 50.0
    assert rows["EURUSD"]["wins"] == 1
    assert rows["EURUSD"]["losses"] == 1
    assert rows["EURUSD"]["win_rate"] == 50.0
    assert rows["EURUSD"]["expectancy"] == 25.0
    assert rows["GOLD"]["breakeven"] == 1
    assert body["totals"]["trade_count"] == 3
    assert body["totals"]["net_pnl"] == 53.0


def test_symbol_performance_marks_an_unregistered_symbol_unpriced(client):
    _store([_closed("SP-4", None, symbol="ZZZ")])

    row = client.get("/api/analytics/symbol-performance").json()["symbols"][0]
    assert row["symbol"] == "ZZZ"
    assert row["registered"] is False
    assert row["unpriced"] == 1
    assert row["priced"] == 0
    assert row["net_pnl"] == 0.0
    # No decided trades means no rate — never a zero that drags an average.
    assert row["win_rate"] == 0.0


def test_symbol_performance_honours_the_account_filter(client):
    with Session(engine) as session:
        first = _account(session, "ftmo", 10_000)
        second = _account(session, "live", 5_000)
        first_id, second_id = first.id, second.id

    _store(
        [
            _closed("SP-5", 100.0, minutes=1, account_id=first_id),
            _closed("SP-6", -40.0, minutes=2, account_id=second_id),
        ]
    )

    body = client.get(
        "/api/analytics/symbol-performance", params={"account_id": first_id}
    ).json()
    assert [row["symbol"] for row in body["symbols"]] == ["EURUSD"]
    assert body["totals"]["net_pnl"] == 100.0


# --- setup × symbol matrix --------------------------------------------------


def test_setup_matrix_groups_setups_by_symbol(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        ob = _tag(session, "ob")
        mistake = _tag(session, "early", category="mistake")
        _store(
            [
                _closed("MX-1", 100.0, minutes=1, tags=[fvg]),
                _closed("MX-2", -40.0, minutes=2, tags=[ob]),
                _closed("MX-3", 60.0, minutes=3, symbol="GOLD", tags=[fvg, ob]),
                _closed("MX-4", 30.0, minutes=4, symbol="GOLD"),
            ],
            session,
        )

    body = client.get("/api/analytics/setup-matrix").json()
    rows = {row["setup"]: row for row in body["rows"]}

    assert body["symbols"] == ["EURUSD", "GOLD"]
    assert rows["fvg"]["net_pnl"] == 160.0
    assert rows["ob"]["net_pnl"] == 20.0
    # A trade with two setups appears in both rows — that is the matrix.
    assert rows["fvg"]["trade_count"] == 2
    assert rows["ob"]["trade_count"] == 2
    # The trade with no setup is its own row so the columns still reconcile.
    assert rows[None]["is_untagged"] is True
    assert rows[None]["net_pnl"] == 30.0
    # Mistake tags never become a setup row.
    assert "early" not in rows

    column_total = sum(column["net_pnl"] for column in body["column_totals"])
    assert column_total == body["grand_total"]["net_pnl"] == 150.0


def test_setup_matrix_cell_carries_the_shared_rules(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        _store(
            [
                _closed("MX-5", 100.0, minutes=1, tags=[fvg]),
                _closed("MX-6", -40.0, minutes=2, tags=[fvg]),
                _closed("MX-7", 3.0, minutes=3, symbol="GOLD", tags=[fvg]),
            ],
            session,
        )

    body = client.get("/api/analytics/setup-matrix").json()
    row = body["rows"][0]
    cells = {cell["symbol"]: cell for cell in row["cells"]}

    assert cells["EURUSD"]["win_rate"] == 50.0
    assert cells["GOLD"]["breakeven"] == 1
    assert cells["GOLD"]["net_pnl"] == 3.0


def test_setup_matrix_omits_a_setup_with_no_closed_trades(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        _tag(session, "unused")
        _store([_closed("MX-8", 50.0, minutes=1, tags=[fvg])], session)

    body = client.get("/api/analytics/setup-matrix").json()
    assert [row["setup"] for row in body["rows"]] == ["fvg"]


# --- expectancy confidence --------------------------------------------------


def test_mean_confidence_matches_the_sample_statistics():
    stats = mean_confidence([100.0, -50.0, 150.0])
    mean = 200.0 / 3.0
    variance = sum((v - mean) ** 2 for v in [100.0, -50.0, 150.0]) / 2.0
    standard_error = math.sqrt(variance) / math.sqrt(3.0)
    margin = 1.959963984540054 * standard_error

    assert stats["sample_size"] == 3
    assert stats["mean"] == 66.67
    assert stats["std_dev"] == round(math.sqrt(variance), 2)
    assert stats["standard_error"] == round(standard_error, 2)
    assert stats["ci_low"] == round(mean - margin, 2)
    assert stats["ci_high"] == round(mean + margin, 2)


def test_mean_confidence_of_one_trade_has_no_interval():
    stats = mean_confidence([25.0])
    assert stats["mean"] == 25.0
    assert stats["std_dev"] is None
    assert stats["ci_low"] is None
    assert stats["ci_high"] is None


def test_mean_confidence_of_nothing_is_empty():
    stats = mean_confidence([])
    assert stats["sample_size"] == 0
    assert stats["mean"] is None


def test_min_sample_size_reads_the_environment(monkeypatch):
    monkeypatch.setenv("MIN_SAMPLE_SIZE", "5")
    assert min_sample_size() == 5

    monkeypatch.setenv("MIN_SAMPLE_SIZE", "not-a-number")
    assert min_sample_size() == 20

    monkeypatch.delenv("MIN_SAMPLE_SIZE", raising=False)
    assert min_sample_size() == 20


def test_setup_confidence_flags_a_thin_setup_and_ranks_the_larger_one_first(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        ob = _tag(session, "ob")
        thin = [_closed(f"CI-T-{i}", net, minutes=i, tags=[fvg]) for i, net in enumerate([100.0, -50.0, 150.0])]
        # 40 decided trades with a modest positive edge.
        fat = [
            _closed(f"CI-F-{i}", 100.0 if i % 2 == 0 else -50.0, minutes=10 + i, tags=[ob])
            for i in range(40)
        ]
        _store(thin + fat, session)

    body = client.get("/api/analytics/setup-confidence").json()
    assert body["min_sample"] == 20
    assert [row["name"] for row in body["tags"]] == ["ob", "fvg"]

    ob_row, fvg_row = body["tags"]
    assert ob_row["decided"] == 40
    assert ob_row["sufficient"] is True
    assert fvg_row["decided"] == 3
    assert fvg_row["sufficient"] is False
    assert body["insufficient"] == 1
    # The thin setup still reports its interval — it just is not ranked.
    assert fvg_row["ci_low"] is not None and fvg_row["ci_high"] is not None


def test_setup_confidence_filters_by_tag(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        ob = _tag(session, "ob")
        _store(
            [
                _closed("CI-1", 100.0, minutes=1, tags=[fvg]),
                _closed("CI-2", -40.0, minutes=2, tags=[ob]),
            ],
            session,
        )

    body = client.get("/api/analytics/setup-confidence", params={"tag": "#fvg"}).json()
    assert [row["name"] for row in body["tags"]] == ["fvg"]


def test_setup_confidence_ignores_unpriced_trades_in_the_mean(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        _store(
            [
                _closed("CI-3", 100.0, minutes=1, tags=[fvg]),
                _closed("CI-4", None, minutes=2, tags=[fvg], symbol="ZZZ"),
            ],
            session,
        )

    row = client.get("/api/analytics/setup-confidence").json()["tags"][0]
    assert row["trade_count"] == 2
    assert row["priced"] == 1
    assert row["unpriced"] == 1
    assert row["expectancy"] == 100.0
    # A single priced trade has no interval to estimate.
    assert row["ci_low"] is None


# --- drawdown by group ------------------------------------------------------


def test_drawdown_curve_tracks_peak_and_trough():
    curve = drawdown_curve([100.0, -150.0, 20.0, 200.0])
    assert curve == {
        "net_pnl": 170.0,
        "peak": 170.0,
        "max_drawdown": -150.0,
        "current_drawdown": 0.0,
    }


def test_drawdown_curve_of_a_losing_series():
    curve = drawdown_curve([-50.0, -25.0])
    assert curve["net_pnl"] == -75.0
    assert curve["peak"] == 0.0
    assert curve["max_drawdown"] == -75.0
    assert curve["current_drawdown"] == -75.0


def test_drawdown_breaks_out_by_account(client):
    with Session(engine) as session:
        first = _account(session, "ftmo", 10_000)
        second = _account(session, "live", 5_000)
        first_id, second_id = first.id, second.id

    _store(
        [
            _closed("DD-1", 100.0, minutes=1, account_id=first_id),
            _closed("DD-2", -150.0, minutes=2, account_id=first_id),
            _closed("DD-3", 20.0, minutes=3, account_id=first_id),
            _closed("DD-4", 200.0, minutes=4, account_id=second_id),
        ]
    )

    body = client.get("/api/analytics/drawdown", params={"group_by": "account"}).json()
    assert body["group_by"] == "account"
    assert body["overall"]["max_drawdown"] == -150.0
    assert body["overall"]["net_pnl"] == 170.0

    groups = {row["label"]: row for row in body["groups"]}
    assert groups["@ftmo"]["max_drawdown"] == -150.0
    assert groups["@ftmo"]["current_drawdown"] == -130.0
    assert groups["@live"]["max_drawdown"] == 0.0


def test_drawdown_breaks_out_by_setup_and_keeps_untagged(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        _store(
            [
                _closed("DD-5", 100.0, minutes=1, tags=[fvg]),
                _closed("DD-6", -150.0, minutes=2, tags=[fvg]),
                _closed("DD-7", 200.0, minutes=3, tags=[fvg]),
                _closed("DD-8", 20.0, minutes=4),
            ],
            session,
        )

    body = client.get("/api/analytics/drawdown", params={"group_by": "setup"}).json()
    groups = {row["label"]: row for row in body["groups"]}

    assert groups["#fvg"]["max_drawdown"] == -150.0
    assert groups["#fvg"]["net_pnl"] == 150.0
    assert groups["Untagged"]["net_pnl"] == 20.0
    # Worst drawdown first.
    assert body["groups"][0]["label"] == "#fvg"


def test_drawdown_rejects_an_unknown_grouping(client):
    response = client.get("/api/analytics/drawdown", params={"group_by": "symbol"})
    assert response.status_code == 422


# --- risk of ruin -----------------------------------------------------------


def test_ruin_probability_is_certain_without_an_edge():
    assert ruin_probability(40.0, 1.0, 100.0) == 1.0


def test_ruin_probability_falls_with_more_units_of_capital():
    fifty = ruin_probability(55.0, 1.5, 50.0)
    hundred = ruin_probability(55.0, 1.5, 100.0)
    assert 0.0 < hundred < fifty < 1.0


def test_ruin_probability_needs_a_risk_figure():
    assert ruin_probability(55.0, 1.5, None) is None
    assert ruin_probability(55.0, 1.5, 0.0) is None


def test_risk_of_ruin_uses_the_account_balance_and_realized_risk(client):
    with Session(engine) as session:
        account = _account(session, "ftmo", 10_000)
        fvg = _tag(session, "fvg")
        _store(
            [
                _closed(
                    "RR-1",
                    500.0,
                    minutes=1,
                    account_id=account.id,
                    tags=[fvg],
                    realized_risk=100.0,
                    initial_risk=50.0,
                ),
                _closed(
                    "RR-2",
                    -100.0,
                    minutes=2,
                    account_id=account.id,
                    tags=[fvg],
                    realized_risk=100.0,
                    initial_risk=50.0,
                ),
                _closed(
                    "RR-3",
                    200.0,
                    minutes=3,
                    account_id=account.id,
                    tags=[fvg],
                    realized_risk=100.0,
                    initial_risk=50.0,
                ),
            ],
            session,
        )

    body = client.get("/api/analytics/risk-of-ruin", params={"min_sample": 3}).json()
    row = body["setups"][0]

    # start 10,000 + 600 net = 10,600; risk is the carried 100, not the planned 50.
    assert body["account_size"] == 10_600.0
    assert body["account_size_source"] == "account_balance"
    assert row["risk_per_trade"] == 100.0
    assert row["risk_source"] == "realized"
    assert row["risk_units"] == 106.0
    assert row["sufficient"] is True
    assert row["risk_of_ruin"] == 0.0


def test_risk_of_ruin_of_a_losing_setup_is_certain(client):
    with Session(engine) as session:
        account = _account(session, "ftmo", 10_000)
        ob = _tag(session, "ob")
        _store(
            [
                _closed("RR-4", -50.0, minutes=1, tags=[ob], realized_risk=100.0),
                _closed("RR-5", -70.0, minutes=2, tags=[ob], realized_risk=100.0),
            ],
            session,
        )

    body = client.get("/api/analytics/risk-of-ruin", params={"min_sample": 2}).json()
    row = body["setups"][0]
    assert row["win_rate"] == 0.0
    assert row["risk_of_ruin"] == 1.0
    assert row["sufficient"] is True


def test_risk_of_ruin_falls_back_to_the_planned_risk(client):
    with Session(engine) as session:
        account = _account(session, "ftmo", 10_000)
        fvg = _tag(session, "fvg")
        _store([_closed("RR-6", 100.0, minutes=1, tags=[fvg], initial_risk=50.0)], session)

    row = client.get("/api/analytics/risk-of-ruin", params={"min_sample": 1}).json()["setups"][0]
    assert row["risk_source"] == "initial"
    assert row["risk_per_trade"] == 50.0


def test_risk_of_ruin_reports_missing_capital(client):
    with Session(engine) as session:
        fvg = _tag(session, "fvg")
        _store([_closed("RR-7", 100.0, minutes=1, tags=[fvg], realized_risk=100.0)], session)

    body = client.get("/api/analytics/risk-of-ruin").json()
    assert body["account_size"] is None
    assert body["account_size_source"] == "missing"
    assert body["detail"]
    assert body["setups"][0]["risk_of_ruin"] is None


def test_risk_of_ruin_accepts_explicit_capital_and_risk(client):
    with Session(engine) as session:
        _account(session, "ftmo", 10_000)
        fvg = _tag(session, "fvg")
        _store([_closed("RR-8", 500.0, minutes=1, tags=[fvg], realized_risk=100.0)], session)

    body = client.get(
        "/api/analytics/risk-of-ruin",
        params={"account_size": 5_000, "risk_per_trade": 250, "min_sample": 1},
    ).json()
    row = body["setups"][0]
    assert body["account_size"] == 5_000.0
    assert body["account_size_source"] == "explicit"
    assert body["risk_per_trade_override"] == 250.0
    assert row["risk_per_trade"] == 250.0
    assert row["risk_source"] == "explicit"
    assert row["risk_units"] == 20.0

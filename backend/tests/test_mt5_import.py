"""Tests for the MT5 statement import: parsing and reconciliation.

A statement is a broker-owned document: the parser has to read the two
table shapes MT5 writes (positions side by side, deals as a flat list), and
a re-import must refresh only the broker fields, never the trader's thesis,
review notes or tags. The same file imported twice has to be a no-op.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.models import Account, Trade
from app.services.mt5_import import (
    StatementError,
    decode_statement,
    import_rows,
    parse_statement,
    resolve_account_id,
)

POSITIONS_CSV = """\
Time,Position,Symbol,Type,Volume,Price,SL,TP,Time,Price,Commission,Swap,Profit
2026.09.20 10:00:00,998877,XAUUSD.,buy,0.10,4000.00,3990.00,4020.00,2026.09.20 10:45:00,4015.00,-3.50,-1.25,150.00
2026.09.21 09:00:00,998878,EURUSD,sell,0.50,1.10000,1.10500,1.09000,2026.09.21 09:30:00,1.09500,0.00,0.00,50.00
2026.09.22 09:00:00,998879,XAUUSD,buy,0.10,4000.00,3990.00,4020.00,,,,0.00,0.00,
"""

DEALS_CSV = """\
Ticket,Time,Type,Direction,Symbol,Volume,Price,Commission,Swap,Profit
1001,2026.10.01 09:00:00,buy,in,XAUUSD,0.10,4000.00,-1.00,0.00,0.00
1002,2026.10.01 09:30:00,sell,out,XAUUSD,0.05,4010.00,-0.50,0.00,50.00
1003,2026.10.01 10:00:00,sell,out,XAUUSD,0.05,4020.00,-0.50,0.00,100.00
1004,2026.10.01 11:00:00,sell,in,XAUUSD,0.10,4030.00,-1.00,0.00,0.00
1005,2026.10.01 11:30:00,buy,out,XAUUSD,0.10,4025.00,-1.00,0.00,50.00
1006,2026.10.01 12:00:00,buy,out,EURUSD,0.10,1.1000,-0.10,0.00,10.00
1007,2026.10.01 13:00:00,buy,inout,XAUUSD,0.10,4040.00,-0.20,0.00,-5.00
"""


def _positions_html(login: str = "51234567") -> str:
    return f"""\
<html><body>
<div>Account: {login}</div>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Balance</td><td>100000</td></tr>
</table>
<table>
  <tr>
    <th>Time</th><th>Position</th><th>Symbol</th><th>Type</th><th>Volume</th>
    <th>Price</th><th>SL</th><th>TP</th><th>Time</th><th>Price</th>
    <th>Commission</th><th>Swap</th><th>Profit</th>
  </tr>
  <tr>
    <td>2026.09.20 10:00:00</td><td>998877</td><td>XAUUSD.</td><td>buy</td><td>0.10</td>
    <td>4000.00</td><td>3990.00</td><td>4020.00</td><td>2026.09.20 10:45:00</td>
    <td>4015.00</td><td>&minus;3.50</td><td>&minus;1.25</td><td>150.00</td>
  </tr>
</table>
</body></html>"""


DEALS_HTML = """\
<html><body>
<table>
  <tr>
    <th>Time</th><th>Deal</th><th>Symbol</th><th>Type</th><th>Direction</th>
    <th>Volume</th><th>Price</th><th>Commission</th><th>Swap</th><th>Profit</th>
  </tr>
  <tr><td>2026.10.01 09:00:00</td><td>2001</td><td>XAUUSD</td><td>buy</td>
    <td>in</td><td>0.10</td><td>4000.00</td><td>-1.00</td><td>0.00</td><td>0.00</td></tr>
  <tr><td>2026.10.01 09:30:00</td><td>2002</td><td>XAUUSD</td><td>sell</td>
    <td>out</td><td>0.10</td><td>4010.00</td><td>-0.50</td><td>0.00</td><td>100.00</td></tr>
  <tr><td>2026.10.01 10:00:00</td><td>2003</td><td>XAUUSD</td><td>buy</td>
    <td>inout</td><td>0.10</td><td>4050.00</td><td>-0.25</td><td>0.00</td><td>-10.00</td></tr>
</table>
</body></html>"""


# --- positions -------------------------------------------------------------


def test_a_positions_csv_is_read_as_one_row_per_closed_position():
    parsed = parse_statement(POSITIONS_CSV, "positions.csv")

    assert parsed.format == "csv"
    assert parsed.account_login is None
    assert len(parsed.rows) == 2  # the open position is not a ledger row
    rows = {row["ticket"]: row for row in parsed.rows}

    gold = rows["998877"]
    assert gold["symbol"] == "XAUUSD"  # trailing broker dot stripped
    assert gold["direction"] == "buy"
    assert gold["size"] == 0.1
    assert gold["entry_price"] == 4000.0
    assert gold["exit_price"] == 4015.0
    assert gold["initial_sl"] == 3990.0
    assert gold["tp"] == 4020.0
    assert gold["entry_time"] == datetime(2026, 9, 20, 10, 0)
    assert gold["exit_time"] == datetime(2026, 9, 20, 10, 45)
    assert gold["gross_pnl"] == 150.0
    assert gold["fees"] == 4.75  # -(commission + swap)
    assert gold["_has_sl"] and gold["_has_tp"] and gold["_has_gross"] and gold["_has_fees"]

    euro = rows["998878"]
    assert euro["direction"] == "sell"
    assert euro["fees"] == 0.0


def test_a_blank_position_ticket_gets_a_stable_synthetic_one():
    csv_text = """\
Time,Position,Symbol,Type,Volume,Price,SL,TP,Time,Price,Commission,Swap,Profit
2026.09.20 10:00:00,,XAUUSD,buy,0.10,4000.00,3990.00,4020.00,2026.09.20 10:45:00,4015.00,0,0,150
"""
    first = parse_statement(csv_text, "positions.csv").rows
    second = parse_statement(csv_text, "positions.csv").rows

    assert first[0]["ticket"] == "MT5-XAUUSD-20260920T100000"
    assert first[0]["ticket"] == second[0]["ticket"]


def test_duplicate_position_tickets_are_made_unique_with_a_suffix():
    csv_text = """\
Time,Position,Symbol,Type,Volume,Price,SL,TP,Time,Price,Commission,Swap,Profit
2026.09.20 10:00:00,111,XAUUSD,buy,0.10,4000.00,3990.00,4020.00,2026.09.20 10:45:00,4015.00,0,0,150
2026.09.20 11:00:00,111,XAUUSD,buy,0.10,4000.00,3990.00,4020.00,2026.09.20 11:45:00,4015.00,0,0,150
"""
    tickets = [row["ticket"] for row in parse_statement(csv_text, "p.csv").rows]
    assert tickets == ["111", "111-2"]


def test_an_html_positions_table_keeps_the_account_login():
    parsed = parse_statement(_positions_html(), "report.html")

    assert parsed.format == "html"
    assert parsed.account_login == "51234567"
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row["ticket"] == "998877"
    assert row["fees"] == 4.75  # &minus;3.50 and &minus;1.25 decoded
    assert row["gross_pnl"] == 150.0


# --- deals -----------------------------------------------------------------


def test_partial_closes_split_into_stable_per_exit_tickets():
    parsed = parse_statement(DEALS_CSV, "deals.csv")
    rows = {row["ticket"]: row for row in parsed.rows}

    # The 0.10 entry is closed by two 0.05 exits: one row per exit.
    assert "MT5-1001-1002" in rows
    assert "MT5-1001-1003" in rows
    first, second = rows["MT5-1001-1002"], rows["MT5-1001-1003"]
    for row in (first, second):
        assert row["symbol"] == "XAUUSD"
        assert row["direction"] == "buy"
        assert row["size"] == 0.05
        assert row["entry_price"] == 4000.0
        assert row["entry_time"] == datetime(2026, 10, 1, 9, 0)
    assert first["exit_price"] == 4010.0 and first["gross_pnl"] == 50.0
    assert second["exit_price"] == 4020.0 and second["gross_pnl"] == 100.0
    # The entry commission is split with the volume, not charged twice.
    assert first["fees"] == 1.0
    assert second["fees"] == 1.0
    # A deal export has no stop or target; the flags keep them from erasing them.
    assert not first["_has_sl"] and not first["_has_tp"]

    # A sell entry is closed by the buy out deal.
    short = rows["MT5-1004-1005"]
    assert short["direction"] == "sell"
    assert short["size"] == 0.1
    assert short["gross_pnl"] == 50.0

    # An unmatched out deal is warned about, not invented into a trade.
    assert all("1006" not in ticket for ticket in rows)
    assert any("no matching entry" in warning for warning in parsed.warnings)


def test_an_inout_deal_is_one_row_and_its_profit_is_not_double_counted():
    parsed = parse_statement(DEALS_CSV, "deals.csv")
    row = next(r for r in parsed.rows if r["ticket"] == "MT5-1007")

    assert row["gross_pnl"] == -5.0  # the deal's own profit, once
    assert row["fees"] == 0.2
    assert row["direction"] == "buy"
    assert row["size"] == 0.1


def test_an_html_deals_table_pairs_the_same_way():
    parsed = parse_statement(DEALS_HTML, "deals.html")

    rows = {row["ticket"]: row for row in parsed.rows}
    assert rows["MT5-2001-2002"]["gross_pnl"] == 100.0
    assert rows["MT5-2001-2002"]["fees"] == 1.5
    assert rows["MT5-2003"]["gross_pnl"] == -10.0
    assert rows["MT5-2003"]["fees"] == 0.25


# --- reading the file ------------------------------------------------------


def test_a_statement_with_no_closed_positions_is_rejected():
    open_only = POSITIONS_CSV.splitlines()[0] + "\n" + POSITIONS_CSV.splitlines()[3] + "\n"
    try:
        parse_statement(open_only, "positions.csv")
    except StatementError as exc:
        assert "No closed positions" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("an open position was imported as a closed trade")

    for text in ("", "   \n", "not,a,statement\n1,2,3\n"):
        try:
            parse_statement(text, "bad.csv")
        except StatementError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"accepted an unreadable statement: {text!r}")


def test_a_utf16_or_cp1252_export_is_decoded():
    assert "Account: 51234567" in decode_statement(
        _positions_html().encode("utf-16")
    )
    assert "Prüfung €" in decode_statement("Prüfung €".encode("cp1252"))
    assert decode_statement(b"\xef\xbb\xbfTicket,Time\n").startswith("Ticket")


# --- reconciliation --------------------------------------------------------


def _rows():
    return parse_statement(POSITIONS_CSV, "positions.csv").rows


def _gold(session: Session) -> Trade:
    trade = session.exec(select(Trade).where(Trade.ticket == "998877")).first()
    assert trade is not None
    return trade


def test_the_first_import_adds_the_trades_with_net_and_r(session):
    result = import_rows(session, _rows())

    assert result["counts"] == {
        "added": 2,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "rows": 2,
    }
    gold = _gold(session)
    assert gold.status == "CLOSED"
    assert gold.gross_pnl == 150.0
    assert gold.fees == 4.75
    assert gold.net_pnl == 145.25
    assert gold.quote_currency == "USD"
    assert gold.net_pnl_usd == 145.25
    assert gold.r_multiple == 1.5
    assert gold.initial_risk == 100.0
    assert gold.realized_risk == 100.0
    assert gold.duration_minutes == 45


def test_importing_the_same_statement_twice_changes_nothing(session):
    first = import_rows(session, _rows())
    second = import_rows(session, _rows())

    assert first["counts"]["added"] == 2
    assert second["counts"] == {
        "added": 0,
        "updated": 0,
        "unchanged": 2,
        "skipped": 0,
        "rows": 2,
    }
    assert session.exec(select(Trade).where(Trade.ticket == "998877")).all()


def test_a_reimport_updates_broker_fields_and_keeps_the_trader_notes(session):
    import_rows(session, _rows())
    gold = _gold(session)
    gold.thesis = "breakout above Asia high"
    gold.review_notes = "waited for the retest"
    session.add(gold)
    session.commit()

    changed = _rows()
    row = next(r for r in changed if r["ticket"] == "998877")
    row["exit_price"] = 4025.0
    row["gross_pnl"] = 200.0
    result = import_rows(session, changed)

    assert result["counts"]["updated"] == 1
    assert result["counts"]["unchanged"] == 1
    detail = next(d for d in result["details"] if d["ticket"] == "998877")
    assert detail["changes"]["exit_price"] == {"from": 4015.0, "to": 4025.0}
    assert detail["changes"]["gross_pnl"] == {"from": 150.0, "to": 200.0}

    session.expire_all()
    gold = _gold(session)
    assert gold.exit_price == 4025.0
    assert gold.net_pnl == 195.25  # 200 - 4.75
    assert gold.thesis == "breakout above Asia high"
    assert gold.review_notes == "waited for the retest"


def test_a_statement_without_sl_and_tp_columns_does_not_erase_them(session):
    import_rows(session, _rows())
    gold = _gold(session)
    assert gold.initial_sl == 3990.0
    assert gold.tp == 4020.0

    # A deal-shaped row carries no stop/target; a changed exit still updates.
    row = _rows()[0]
    row.update({"_has_sl": False, "_has_tp": False, "exit_price": 4025.0})
    import_rows(session, [row])

    session.expire_all()
    gold = _gold(session)
    assert gold.initial_sl == 3990.0
    assert gold.current_sl == 3990.0
    assert gold.tp == 4020.0
    assert gold.exit_price == 4025.0


def test_update_existing_false_skips_an_existing_ticket(session):
    import_rows(session, _rows())
    changed = _rows()
    changed[0]["exit_price"] = 4025.0

    result = import_rows(session, changed, update_existing=False)

    assert result["counts"]["skipped"] == 2
    detail = next(d for d in result["details"] if d["ticket"] == "998877")
    assert detail == {
        "ticket": "998877",
        "action": "skipped",
        "reason": "ticket already exists",
    }
    session.expire_all()
    assert _gold(session).exit_price == 4015.0


def test_an_import_claims_an_unassigned_trade_but_never_moves_a_filed_one(session):
    account = Account(alias="ftmo100k", firm="FTMO", login="51234567")
    session.add(account)
    session.commit()
    session.refresh(account)

    import_rows(session, _rows(), account_id=account.id)
    session.expire_all()
    assert _gold(session).account_id == account.id

    import_rows(session, _rows(), account_id=None)
    session.expire_all()
    assert _gold(session).account_id == account.id


def test_the_explicit_account_wins_over_the_statement_login(session):
    by_login = Account(alias="login-acct", login="51234567")
    explicit = Account(alias="explicit-acct", login="99999999")
    session.add(by_login)
    session.add(explicit)
    session.commit()
    session.refresh(by_login)
    session.refresh(explicit)

    assert resolve_account_id(session, explicit.id, "51234567") == explicit.id
    assert resolve_account_id(session, None, "51234567") == by_login.id
    assert resolve_account_id(session, None, "00000000") is None
    assert resolve_account_id(session, None, None) is None


# --- the API surface -------------------------------------------------------


def test_the_import_endpoint_stores_the_run_and_reports_the_counts(client, session):
    account = client.post(
        "/api/accounts", json={"alias": "ftmo100k", "firm": "FTMO"}
    ).json()

    response = client.post(
        "/api/trades/import/mt5",
        files={"file": ("positions.csv", POSITIONS_CSV, "text/csv")},
        data={"account_id": str(account["id"])},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "csv"
    assert body["account_id"] == account["id"]
    assert body["counts"]["added"] == 2

    runs = client.get("/api/trades/imports").json()["runs"]
    assert runs[0]["id"] == body["run_id"]
    assert runs[0]["added"] == 2

    again = client.post(
        "/api/trades/import/mt5",
        files={"file": ("positions.csv", POSITIONS_CSV, "text/csv")},
        data={"account_id": str(account["id"])},
    )
    assert again.json()["counts"]["unchanged"] == 2

    bad = client.post(
        "/api/trades/import/mt5",
        files={"file": ("notes.csv", "just some text", "text/csv")},
    )
    assert bad.status_code == 422
    assert client.get("/api/trades/imports").json()["runs"][0]["error"]


def test_the_import_endpoint_reads_the_account_from_the_html_report(client):
    client.post(
        "/api/accounts",
        json={"alias": "report-acct", "firm": "FTMO", "login": "51234567"},
    )

    response = client.post(
        "/api/trades/import/mt5",
        files={"file": ("report.html", _positions_html(), "text/html")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["account_login"] == "51234567"
    assert body["account_id"] is not None
    assert body["counts"]["added"] == 1

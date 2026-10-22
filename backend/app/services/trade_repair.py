"""Repair closed trades that have no gross P&L (Phase 8).

Rows created before the Phase 3 backfill fix can carry prices but no
money. This one-shot repair prices each row from the symbol registry and
restores the ``net = gross - fees`` invariant.

Rules, in order:

- a row with no exit price (or no entry price, size or direction) is
  *skipped* — a guess is worse than admitting the row is incomplete;
- a row whose symbol has no registry contract is *unpriced* — no amount
  can be derived for an instrument whose contract size is unknown;
- a net the trader supplied is never overwritten: the gross is recovered
  from it (``gross = net + fees``) and the net is left byte-for-byte as it
  was;
- every other row gets a registry-priced gross and ``net = gross - fees``.

The repair is idempotent: only rows with a missing gross are considered,
so a second run has nothing left to write.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import Trade
from app.services.symbol_registry import (
    direction_sign,
    estimate_gross_quote_pnl,
    find_spec,
)
from app.services.trade_money import set_trade_pnl, sync_trade_usd


def _blocking_issue(trade: Trade) -> str | None:
    """Why this row cannot be priced at all, or None when it can."""
    if trade.exit_price is None:
        return "no exit price"
    if trade.entry_price is None:
        return "no entry price"
    if trade.size is None or trade.size <= 0:
        return "no size"
    if direction_sign(trade.direction) == 0:
        return "no direction"
    if not str(trade.symbol or "").strip():
        return "no symbol"
    return None


def repair_unpriced_trades(session: Session, apply: bool = False) -> dict:
    """Price every CLOSED row whose gross is missing. Dry-run by default."""
    trades = session.exec(
        select(Trade)
        .where(Trade.status == "CLOSED", Trade.gross_pnl.is_(None))
        .order_by(Trade.id)
    ).all()

    results: list[dict] = []
    repairable = repaired = skipped = unpriced = kept_net = 0

    for trade in trades:
        issue = _blocking_issue(trade)
        if issue is not None:
            skipped += 1
            results.append({"ticket": trade.ticket, "action": "skipped", "reason": issue})
            continue

        if find_spec(session, trade.symbol) is None:
            unpriced += 1
            results.append(
                {
                    "ticket": trade.ticket,
                    "action": "unpriced",
                    "reason": f"no contract for {str(trade.symbol or '').upper()}",
                }
            )
            continue

        fees = float(trade.fees or 0.0)
        supplied_net = trade.net_pnl
        if supplied_net is not None:
            # Keep the trader's net exactly; recover the gross behind it.
            gross = round(supplied_net + fees, 2)
            kept_net += 1
        else:
            gross = estimate_gross_quote_pnl(
                session,
                trade.direction,
                trade.symbol,
                trade.size,
                trade.entry_price,
                trade.exit_price,
            )
        if gross is None:
            unpriced += 1
            results.append(
                {
                    "ticket": trade.ticket,
                    "action": "unpriced",
                    "reason": "the registry could not price this row",
                }
            )
            continue

        repairable += 1
        action = "would_repair"
        if apply:
            set_trade_pnl(session, trade, gross, fees)
            if supplied_net is not None:
                trade.net_pnl = supplied_net
                sync_trade_usd(session, trade)
            trade.updated_at = datetime.now(timezone.utc)
            session.add(trade)
            repaired += 1
            action = "repaired"

        results.append(
            {
                "ticket": trade.ticket,
                "action": action,
                "gross_pnl": gross,
                "net_pnl": supplied_net if supplied_net is not None else round(gross - fees, 2),
                "kept_net": supplied_net is not None,
            }
        )

    if apply and repaired:
        session.commit()

    return {
        "apply": apply,
        "scanned": len(trades),
        "repairable": repairable,
        "repaired": repaired,
        "skipped": skipped,
        "unpriced": unpriced,
        "kept_net": kept_net,
        "results": results,
    }

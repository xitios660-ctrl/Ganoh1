"""
Read-only Mongo finance tools for WhatsApp AI (ETAPA 7).

Design decision:
  Intent detect → Mongo read-only queries → inject structured facts into the
  OpenAI prompt → model only formats/explains. No OpenAI function-calling
  (simpler, fully unit-testable with a fake DB, no tool schema drift).

Rules:
  - NEVER invent numbers; if query fails or returns empty, report no data.
  - NEVER mutate finance collections (no insert/update/delete/upsert here).
  - Sensitive mutations stay blocked in whatsapp_ai (Gestor confirmation).
  - Timezone for "hoje" / morning shift: America/Sao_Paulo.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pytz

logger = logging.getLogger("whatsapp_finance")

BRAZIL_TZ = pytz.timezone("America/Sao_Paulo")

STORES = ("runner", "gym-londres")
STORE_ALIASES = {
    "runner": "runner",
    "runer": "runner",
    "café runner": "runner",
    "cafe runner": "runner",
    "gym": "gym-londres",
    "gym londres": "gym-londres",
    "gym-londres": "gym-londres",
    "londres": "gym-londres",
    "gymlondres": "gym-londres",
}
STORE_LABELS = {
    "runner": "Runner",
    "gym-londres": "GYM Londres",
}

# Intent names
INTENT_SALES_TODAY = "sales_today"
INTENT_PIX_TODAY = "pix_today"
INTENT_CASH_TODAY = "cash_today"
INTENT_BY_STORE = "sales_by_store"
INTENT_DEBTS = "debts_list"
INTENT_DEBT_CUSTOMER = "debt_customer"
INTENT_PRAZO_PAYMENTS_TODAY = "prazo_payments_today"
INTENT_MORNING_CLOSE = "morning_close"
INTENT_CASH_DRAWER = "cash_drawer"
INTENT_LOW_STOCK = "low_stock"
INTENT_DAY_SUMMARY = "day_summary"
INTENT_UNKNOWN_FINANCE = "unknown_finance"

READY_STATUSES = ("ready", "delivered")

# Injected async fetcher for tests: (intent, text) -> facts dict
_fetcher_override: Optional[Callable[..., Any]] = None
# Optional motor-like db (set from server)
_db = None


@dataclass
class IntentResult:
    intent: str
    store: Optional[str] = None  # runner | gym-londres | None (= all)
    customer_hint: Optional[str] = None
    payment_focus: Optional[str] = None  # pix | cash | ...
    raw_text: str = ""


@dataclass
class FinanceFacts:
    intent: str
    ok: bool
    label: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    empty: bool = False

    def to_prompt_block(self) -> str:
        """Serialize facts for the system/user prompt (AI must not invent beyond this)."""
        if not self.ok:
            return (
                f"[DADOS OFICIAIS DO SISTEMA — falha]\n"
                f"intent={self.intent}\n"
                f"erro={self.error or 'consulta indisponível'}\n"
                f"Instrução: diga que não foi possível obter o dado agora; NÃO invente números."
            )
        if self.empty:
            return (
                f"[DADOS OFICIAIS DO SISTEMA — sem registros]\n"
                f"intent={self.intent}\n"
                f"label={self.label}\n"
                f"Instrução: diga que não há dados para o período/filtro; NÃO invente números."
            )
        lines = [
            "[DADOS OFICIAIS DO SISTEMA — use SOMENTE estes valores]",
            f"intent={self.intent}",
            f"label={self.label}",
        ]
        for key, value in self.data.items():
            lines.append(f"{key}={_fmt_value(value)}")
        lines.append(
            "Instrução: formate/explique estes fatos em português. "
            "NÃO invente, NÃO some valores que não estejam listados."
        )
        return "\n".join(lines)


def _fmt_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return "; ".join(_fmt_value(v) for v in value)
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}:{_fmt_value(v)}" for k, v in value.items()) + "}"
    return str(value)


def set_db(database) -> None:
    """Wire Motor DB from server startup / inbound path. Read-only use only."""
    global _db
    _db = database


def get_db():
    return _db


def set_fetcher_override(fn: Optional[Callable[..., Any]]) -> None:
    """Test helper — inject async/sync facts producer; pass None to clear."""
    global _fetcher_override
    _fetcher_override = fn


def _parse_iso_utc(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _filter_since(items: Sequence[dict], since_dt: Optional[datetime], field: str = "created_at") -> List[dict]:
    if not since_dt:
        return list(items)
    out = []
    for item in items:
        parsed = _parse_iso_utc(item.get(field))
        if parsed is not None and parsed >= since_dt:
            out.append(item)
    return out


def brazil_today_bounds() -> Tuple[datetime, datetime, str]:
    """Return (today_start_utc, now_brazil, date_str YYYY-MM-DD) for America/Sao_Paulo."""
    now_brazil = datetime.now(BRAZIL_TZ)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    return today_utc, now_brazil, today_brazil.strftime("%Y-%m-%d")


def detect_store(text: str) -> Optional[str]:
    if not text:
        return None
    lower = text.lower()
    # Longer aliases first
    for alias in sorted(STORE_ALIASES.keys(), key=len, reverse=True):
        if alias in lower:
            return STORE_ALIASES[alias]
    return None


_DEBT_WHO_RE = re.compile(
    r"\b(quem\s+est[aá]\s+devendo|quem\s+deve|lista\s+de\s+d[ií]vidas|devedores|inadimpl)\b",
    re.IGNORECASE,
)
_DEBT_HOW_MUCH_RE = re.compile(
    r"(?:quanto\s+(?:que\s+)?(?:a|o|à|ao)?\s*)?([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,40}?)\s+"
    r"(?:est[aá]\s+)?dev(?:e|endo)|(?:d[ií]vida|saldo)\s+(?:d[eo]|da|do)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,40})",
    re.IGNORECASE,
)
_PIX_RE = re.compile(r"\b(pix)\b", re.IGNORECASE)
_CASH_RE = re.compile(r"\b(dinheiro|esp[eé]cie|cash)\b", re.IGNORECASE)
_SALES_RE = re.compile(
    r"\b(venda|vendas|faturamento|quanto\s+(fez|vendeu|entrou)|total\s+do\s+dia|resumo\s+do\s+dia)\b",
    re.IGNORECASE,
)
_MORNING_RE = re.compile(
    r"\b(fechamento\s+da\s+manh[aã]|turno\s+da\s+manh[aã]|manh[aã]|06\s*[:h]\s*00)\b",
    re.IGNORECASE,
)
_DRAWER_RE = re.compile(
    r"\b(caixa|saldo\s+do\s+caixa|diferen[cç]a\s+no\s+caixa|confer[eê]ncia\s+de\s+caixa)\b",
    re.IGNORECASE,
)
_STOCK_RE = re.compile(r"\b(estoque\s+baixo|falta\s+de\s+estoque|itens?\s+em\s+falta|low\s*stock)\b", re.IGNORECASE)
_PRAZO_PAY_RE = re.compile(
    r"\b(pagamento[s]?\s+de\s+prazo|prazo\s+pago|receberam\s+prazo|pagou\s+prazo|pagamentos?\s+prazo)\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(r"\b(resumo\s+do\s+dia|resumo\s+hoje|fechamento\s+do\s+dia)\b", re.IGNORECASE)
_BY_STORE_RE = re.compile(r"\b(por\s+loja|por\s+vendedor|cada\s+loja|runner|gym|londres)\b", re.IGNORECASE)


def detect_intent(text: str) -> IntentResult:
    """Map free-text question to a finance intent (no DB)."""
    text = (text or "").strip()
    store = detect_store(text)
    result = IntentResult(intent=INTENT_UNKNOWN_FINANCE, store=store, raw_text=text)

    if _DEBT_WHO_RE.search(text):
        result.intent = INTENT_DEBTS
        return result

    m = _DEBT_HOW_MUCH_RE.search(text)
    if m and ("dev" in text.lower() or "dívida" in text.lower() or "divida" in text.lower()):
        hint = (m.group(1) or m.group(2) or "").strip()
        # Avoid capturing generic words
        bad = {"o", "a", "cliente", "ele", "ela", "hoje", "ainda", "quanto"}
        if hint and hint.lower() not in bad and len(hint) >= 2:
            result.intent = INTENT_DEBT_CUSTOMER
            result.customer_hint = hint.strip(" ?!.")
            return result

    if _STOCK_RE.search(text):
        result.intent = INTENT_LOW_STOCK
        return result

    if _PRAZO_PAY_RE.search(text):
        result.intent = INTENT_PRAZO_PAYMENTS_TODAY
        return result

    if _MORNING_RE.search(text) and (_SALES_RE.search(text) or "fechamento" in text.lower() or "turno" in text.lower()):
        result.intent = INTENT_MORNING_CLOSE
        return result

    if _DRAWER_RE.search(text) and not _SALES_RE.search(text):
        result.intent = INTENT_CASH_DRAWER
        return result

    if _SUMMARY_RE.search(text):
        result.intent = INTENT_DAY_SUMMARY
        return result

    if _PIX_RE.search(text) and (_SALES_RE.search(text) or "quanto" in text.lower() or "total" in text.lower() or "hoje" in text.lower()):
        result.intent = INTENT_PIX_TODAY
        result.payment_focus = "pix"
        return result

    if _CASH_RE.search(text) and (_SALES_RE.search(text) or "quanto" in text.lower() or "hoje" in text.lower()):
        result.intent = INTENT_CASH_TODAY
        result.payment_focus = "cash"
        return result

    if _BY_STORE_RE.search(text) and _SALES_RE.search(text):
        result.intent = INTENT_BY_STORE
        return result

    if _SALES_RE.search(text) or "hoje" in text.lower() and ("vendeu" in text.lower() or "venda" in text.lower()):
        result.intent = INTENT_SALES_TODAY
        return result

    if _PIX_RE.search(text):
        result.intent = INTENT_PIX_TODAY
        result.payment_focus = "pix"
        return result

    if _DRAWER_RE.search(text):
        result.intent = INTENT_CASH_DRAWER
        return result

    return result


async def _to_list(cursor, limit: int = 5000) -> List[dict]:
    if cursor is None:
        return []
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(limit)
    if isinstance(cursor, list):
        return cursor[:limit]
    return list(cursor)[:limit]


async def _find(db, collection: str, query: dict, projection: Optional[dict] = None, limit: int = 5000) -> List[dict]:
    coll = getattr(db, collection, None)
    if coll is None and hasattr(db, "__getitem__"):
        coll = db[collection]
    if coll is None:
        return []
    cursor = coll.find(query, projection or {"_id": 0})
    if hasattr(cursor, "sort"):
        try:
            cursor = cursor.sort("created_at", -1)
        except Exception:
            pass
    return await _to_list(cursor, limit)


async def _find_one(db, collection: str, query: dict, projection: Optional[dict] = None) -> Optional[dict]:
    coll = getattr(db, collection, None)
    if coll is None and hasattr(db, "__getitem__"):
        coll = db[collection]
    if coll is None:
        return None
    doc = await coll.find_one(query, projection or {"_id": 0})
    return doc


def _round_money(value: float) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_orders(orders: List[dict]) -> Dict[str, Any]:
    by_payment = {"pix": 0.0, "debit": 0.0, "credit": 0.0, "cash": 0.0, "prazo": 0.0, "voucher": 0.0}
    total = 0.0
    count = 0
    morning = {"total": 0.0, "count": 0, "by_payment": {"pix": 0.0, "debit": 0.0, "credit": 0.0, "cash": 0.0, "voucher": 0.0}}
    afternoon = {"total": 0.0, "count": 0, "by_payment": {"pix": 0.0, "debit": 0.0, "credit": 0.0, "cash": 0.0, "voucher": 0.0}}

    for order in orders:
        payment = order.get("payment_method") or "cash"
        amount = _round_money(order.get("total", 0))
        count += 1
        if payment != "prazo":
            by_payment[payment] = by_payment.get(payment, 0.0) + amount
            total += amount

        created_at = order.get("created_at", "")
        try:
            order_time = _parse_iso_utc(created_at)
            if order_time is None:
                raise ValueError("bad ts")
            hour = order_time.astimezone(BRAZIL_TZ).hour
            bucket = morning if 6 <= hour < 14 else afternoon
            if payment != "prazo":
                bucket["total"] += amount
                bucket["count"] += 1
                if payment in bucket["by_payment"]:
                    bucket["by_payment"][payment] += amount
        except Exception:
            if payment != "prazo":
                afternoon["total"] += amount
                afternoon["count"] += 1
                if payment in afternoon["by_payment"]:
                    afternoon["by_payment"][payment] += amount

    return {
        "total": _round_money(total),
        "order_count": count,
        "by_payment_method": {k: _round_money(v) for k, v in by_payment.items()},
        "shift_morning": {
            "label": "06:00-14:00",
            "total": _round_money(morning["total"]),
            "count": morning["count"],
            "by_payment": {k: _round_money(v) for k, v in morning["by_payment"].items()},
        },
        "shift_afternoon": {
            "label": "14:00-22:00",
            "total": _round_money(afternoon["total"]),
            "count": afternoon["count"],
            "by_payment": {k: _round_money(v) for k, v in afternoon["by_payment"].items()},
        },
    }


async def _orders_today(db, store: Optional[str], today_utc: datetime) -> List[dict]:
    query: Dict[str, Any] = {"status": {"$in": list(READY_STATUSES)}}
    if store:
        query["store"] = store
    # Avoid string $gte on mixed offsets — filter in Python (same as server.get_today_cash)
    orders = await _find(db, "orders", query, {"_id": 0}, limit=5000)
    return _filter_since(orders, today_utc)


async def _pix_adjustments_today(db, store: Optional[str], today_utc: datetime) -> List[dict]:
    query: Dict[str, Any] = {"removed": {"$ne": True}}
    if store:
        query["store"] = store
    rows = await _find(db, "pix_adjustments", query, {"_id": 0}, limit=2000)
    return _filter_since(rows, today_utc)


async def query_sales_bundle(db, store: Optional[str] = None) -> FinanceFacts:
    today_utc, now_brazil, date_str = brazil_today_bounds()
    try:
        stores = [store] if store else list(STORES)
        per_store = {}
        combined_orders: List[dict] = []
        pix_manual_total = 0.0
        for s in stores:
            orders = await _orders_today(db, s, today_utc)
            pix_adj = await _pix_adjustments_today(db, s, today_utc)
            agg = _aggregate_orders(orders)
            pix_manual = _round_money(sum(a.get("amount", 0) for a in pix_adj))
            agg["by_payment_method"]["pix"] = _round_money(agg["by_payment_method"].get("pix", 0) + pix_manual)
            agg["total"] = _round_money(agg["total"] + pix_manual)
            agg["pix_manual_adjustments"] = pix_manual
            agg["store"] = s
            agg["store_label"] = STORE_LABELS.get(s, s)
            per_store[s] = agg
            combined_orders.extend(orders)
            pix_manual_total += pix_manual

        if store:
            data = per_store[store]
            empty = data["order_count"] == 0 and data.get("pix_manual_adjustments", 0) == 0
            return FinanceFacts(
                intent=INTENT_SALES_TODAY,
                ok=True,
                label=f"Vendas de hoje ({STORE_LABELS.get(store, store)}) — {date_str}",
                data={
                    "date": date_str,
                    "timezone": "America/Sao_Paulo",
                    "store": store,
                    "store_label": STORE_LABELS.get(store, store),
                    "total_vendas_rs": data["total"],
                    "qtd_pedidos": data["order_count"],
                    "pix_rs": data["by_payment_method"].get("pix", 0),
                    "dinheiro_rs": data["by_payment_method"].get("cash", 0),
                    "debito_rs": data["by_payment_method"].get("debit", 0),
                    "credito_rs": data["by_payment_method"].get("credit", 0),
                    "voucher_rs": data["by_payment_method"].get("voucher", 0),
                    "prazo_registrado_rs": data["by_payment_method"].get("prazo", 0),
                    "pix_manual_rs": data.get("pix_manual_adjustments", 0),
                    "manha_total_rs": data["shift_morning"]["total"],
                    "manha_pedidos": data["shift_morning"]["count"],
                    "tarde_total_rs": data["shift_afternoon"]["total"],
                    "tarde_pedidos": data["shift_afternoon"]["count"],
                    "nota": "Prazo não entra no total de vendas à vista.",
                },
                empty=empty,
            )

        grand = _aggregate_orders(combined_orders)
        grand["by_payment_method"]["pix"] = _round_money(grand["by_payment_method"].get("pix", 0) + pix_manual_total)
        grand["total"] = _round_money(grand["total"] + pix_manual_total)
        empty = grand["order_count"] == 0 and pix_manual_total == 0
        by_store_totals = {
            STORE_LABELS.get(s, s): per_store[s]["total"] for s in stores
        }
        return FinanceFacts(
            intent=INTENT_SALES_TODAY,
            ok=True,
            label=f"Vendas de hoje (todas as lojas) — {date_str}",
            data={
                "date": date_str,
                "timezone": "America/Sao_Paulo",
                "total_vendas_rs": grand["total"],
                "qtd_pedidos": grand["order_count"],
                "pix_rs": grand["by_payment_method"].get("pix", 0),
                "dinheiro_rs": grand["by_payment_method"].get("cash", 0),
                "debito_rs": grand["by_payment_method"].get("debit", 0),
                "credito_rs": grand["by_payment_method"].get("credit", 0),
                "voucher_rs": grand["by_payment_method"].get("voucher", 0),
                "pix_manual_rs": _round_money(pix_manual_total),
                "por_loja_rs": by_store_totals,
                "manha_total_rs": grand["shift_morning"]["total"],
                "tarde_total_rs": grand["shift_afternoon"]["total"],
                "nota": "Prazo não entra no total de vendas à vista. Breakdown por vendedor individual não disponível — use por loja.",
            },
            empty=empty,
        )
    except Exception as exc:
        logger.warning("finance sales query failed: %s", type(exc).__name__)
        return FinanceFacts(intent=INTENT_SALES_TODAY, ok=False, label="Vendas hoje", error="consulta_falhou")


async def query_payment_focus(db, store: Optional[str], payment: str, intent: str) -> FinanceFacts:
    bundle = await query_sales_bundle(db, store=store)
    if not bundle.ok:
        return FinanceFacts(intent=intent, ok=False, label=bundle.label, error=bundle.error)
    key_map = {"pix": "pix_rs", "cash": "dinheiro_rs"}
    focus_key = key_map.get(payment, payment)
    amount = bundle.data.get(focus_key, 0)
    label = "PIX hoje" if payment == "pix" else "Dinheiro hoje"
    if store:
        label = f"{label} ({STORE_LABELS.get(store, store)})"
    return FinanceFacts(
        intent=intent,
        ok=True,
        label=label,
        data={
            "date": bundle.data.get("date"),
            "timezone": "America/Sao_Paulo",
            "store": store or "all",
            "metodo": payment,
            "total_rs": amount,
            "total_vendas_dia_rs": bundle.data.get("total_vendas_rs"),
            "qtd_pedidos": bundle.data.get("qtd_pedidos"),
            "pix_manual_rs": bundle.data.get("pix_manual_rs", 0) if payment == "pix" else 0,
        },
        empty=bundle.empty or _round_money(amount) == 0,
    )


async def query_debts(db, store: Optional[str] = None, customer_hint: Optional[str] = None) -> FinanceFacts:
    try:
        query: Dict[str, Any] = {
            "payment_method": "prazo",
            "prazo_paid": {"$ne": True},
        }
        if store:
            query["store"] = store
        orders = await _find(db, "orders", query, {"_id": 0}, limit=2000)

        debts: Dict[str, Dict[str, Any]] = {}
        for order in orders:
            name = order.get("customer_name") or "Desconhecido"
            order_total = _round_money(order.get("total", 0))
            partial = _round_money(order.get("partial_paid", 0))
            remaining = _round_money(order_total - partial)
            if remaining <= 0:
                continue
            if customer_hint and customer_hint.lower() not in name.lower():
                continue
            if name not in debts:
                debts[name] = {
                    "name": name,
                    "total_rs": 0.0,
                    "order_count": 0,
                    "store": order.get("store", ""),
                }
            debts[name]["total_rs"] = _round_money(debts[name]["total_rs"] + remaining)
            debts[name]["order_count"] += 1

        ranked = sorted(debts.values(), key=lambda d: d["total_rs"], reverse=True)
        if customer_hint:
            if not ranked:
                return FinanceFacts(
                    intent=INTENT_DEBT_CUSTOMER,
                    ok=True,
                    label=f"Dívida de '{customer_hint}'",
                    data={"customer_hint": customer_hint, "encontrado": False},
                    empty=True,
                )
            top = ranked[0]
            return FinanceFacts(
                intent=INTENT_DEBT_CUSTOMER,
                ok=True,
                label=f"Dívida de {top['name']}",
                data={
                    "cliente": top["name"],
                    "total_deve_rs": top["total_rs"],
                    "qtd_pedidos_abertos": top["order_count"],
                    "loja": STORE_LABELS.get(top["store"], top["store"]),
                },
                empty=False,
            )

        total = _round_money(sum(d["total_rs"] for d in ranked))
        # Cap list for prompt size
        top_list = [
            f"{d['name']}: R$ {d['total_rs']:.2f} ({d['order_count']} ped.)"
            for d in ranked[:15]
        ]
        return FinanceFacts(
            intent=INTENT_DEBTS,
            ok=True,
            label="Quem está devendo (prazo em aberto)",
            data={
                "customer_count": len(ranked),
                "total_prazo_aberto_rs": total,
                "store_filter": store or "all",
                "top_devedores": top_list or ["(nenhum)"],
            },
            empty=len(ranked) == 0,
        )
    except Exception as exc:
        logger.warning("finance debts query failed: %s", type(exc).__name__)
        return FinanceFacts(intent=INTENT_DEBTS, ok=False, label="Dívidas", error="consulta_falhou")


async def query_prazo_payments_today(db, store: Optional[str] = None) -> FinanceFacts:
    today_utc, _, date_str = brazil_today_bounds()
    try:
        query: Dict[str, Any] = {}
        if store:
            query["store"] = store
        full = _filter_since(await _find(db, "prazo_payments", query, {"_id": 0}, 2000), today_utc)
        partial = _filter_since(await _find(db, "prazo_partial_payments", query, {"_id": 0}, 2000), today_utc)
        all_pay = full + partial
        totals = {"cash": 0.0, "pix": 0.0, "debit": 0.0, "credit": 0.0}
        for p in all_pay:
            method = p.get("payment_method") or "cash"
            if method not in totals:
                totals[method] = 0.0
            totals[method] = _round_money(totals[method] + _round_money(p.get("amount", 0)))
        grand = _round_money(sum(totals.values()))
        samples = [
            f"{p.get('customer_name', '?')}: R$ {_round_money(p.get('amount', 0)):.2f} ({p.get('payment_method', '?')})"
            for p in sorted(all_pay, key=lambda x: x.get("created_at", ""), reverse=True)[:10]
        ]
        return FinanceFacts(
            intent=INTENT_PRAZO_PAYMENTS_TODAY,
            ok=True,
            label=f"Pagamentos de prazo hoje — {date_str}",
            data={
                "date": date_str,
                "qtd_pagamentos": len(all_pay),
                "total_rs": grand,
                "por_metodo_rs": {k: _round_money(v) for k, v in totals.items()},
                "amostras": samples or ["(nenhum)"],
                "store_filter": store or "all",
            },
            empty=len(all_pay) == 0,
        )
    except Exception as exc:
        logger.warning("finance prazo payments query failed: %s", type(exc).__name__)
        return FinanceFacts(
            intent=INTENT_PRAZO_PAYMENTS_TODAY, ok=False, label="Pagamentos prazo", error="consulta_falhou"
        )


async def query_morning_close(db, store: Optional[str] = None) -> FinanceFacts:
    bundle = await query_sales_bundle(db, store=store)
    if not bundle.ok:
        return FinanceFacts(intent=INTENT_MORNING_CLOSE, ok=False, label="Fechamento manhã", error=bundle.error)
    morning_total = bundle.data.get("manha_total_rs", 0)
    morning_count = bundle.data.get("manha_pedidos", bundle.data.get("qtd_pedidos", 0))
    # When all-stores, shift fields exist; for single store too
    if "manha_pedidos" not in bundle.data and store:
        # already in single-store branch
        pass
    return FinanceFacts(
        intent=INTENT_MORNING_CLOSE,
        ok=True,
        label=f"Fechamento da manhã (06:00-14:00) — {bundle.data.get('date')}",
        data={
            "date": bundle.data.get("date"),
            "timezone": "America/Sao_Paulo",
            "turno": "06:00-14:00",
            "store": store or "all",
            "total_rs": morning_total,
            "qtd_pedidos": bundle.data.get("manha_pedidos", 0),
            "pix_dia_rs": bundle.data.get("pix_rs"),
            "dinheiro_dia_rs": bundle.data.get("dinheiro_rs"),
            "total_dia_rs": bundle.data.get("total_vendas_rs"),
            "nota": "Valores do turno manhã baseados em horário America/Sao_Paulo.",
        },
        empty=_round_money(morning_total) == 0 and int(bundle.data.get("manha_pedidos") or 0) == 0,
    )


async def query_cash_drawer(db, store: Optional[str] = None) -> FinanceFacts:
    """Expected cash drawer balance from system (not physical count)."""
    today_utc, now_brazil, date_str = brazil_today_bounds()
    stores = [store] if store else list(STORES)
    try:
        rows = []
        for s in stores:
            config = await _find_one(db, "cash_drawer_config", {"store": s}, {"_id": 0}) or {}
            initial = _round_money(config.get("balance", 0))
            last_reset_at = config.get("last_reset_at")
            last_reset_dt = _parse_iso_utc(last_reset_at)

            cash_orders = await _find(
                db,
                "orders",
                {
                    "store": s,
                    "status": {"$in": list(READY_STATUSES)},
                    "payment_method": "cash",
                    "synthetic": {"$ne": True},
                },
                {"_id": 0, "total": 1, "created_at": 1},
                10000,
            )
            cash_orders = _filter_since(cash_orders, last_reset_dt)
            total_cash_sales = _round_money(sum(o.get("total", 0) for o in cash_orders))

            prazo_q = {"store": s, "payment_method": "cash"}
            prazo_full = _filter_since(
                await _find(db, "prazo_payments", prazo_q, {"_id": 0, "amount": 1, "created_at": 1}, 5000),
                last_reset_dt,
            )
            prazo_partial = _filter_since(
                await _find(db, "prazo_partial_payments", prazo_q, {"_id": 0, "amount": 1, "created_at": 1}, 5000),
                last_reset_dt,
            )
            credit_topups = _filter_since(
                await _find(db, "cash_credit_topups", prazo_q, {"_id": 0, "amount": 1, "created_at": 1}, 5000),
                last_reset_dt,
            )
            total_prazo_cash = _round_money(
                sum(p.get("amount", 0) for p in prazo_full)
                + sum(p.get("amount", 0) for p in prazo_partial)
                + sum(t.get("amount", 0) for t in credit_topups)
            )
            withdrawals = _filter_since(
                await _find(db, "cash_withdrawals", {"store": s}, {"_id": 0}, 5000),
                last_reset_dt,
            )
            total_withdrawn = _round_money(sum(w.get("amount", 0) for w in withdrawals))
            current = _round_money(initial + total_cash_sales + total_prazo_cash - total_withdrawn)
            today_cash_in = _round_money(sum(o.get("total", 0) for o in _filter_since(cash_orders, today_utc)))
            rows.append(
                {
                    "store": s,
                    "store_label": STORE_LABELS.get(s, s),
                    "saldo_esperado_rs": current,
                    "fundo_inicial_rs": initial,
                    "vendas_dinheiro_desde_reset_rs": total_cash_sales,
                    "prazo_em_dinheiro_desde_reset_rs": total_prazo_cash,
                    "saques_desde_reset_rs": total_withdrawn,
                    "dinheiro_hoje_rs": today_cash_in,
                    "last_reset_at": last_reset_at or "(nunca)",
                }
            )

        if store:
            r = rows[0]
            return FinanceFacts(
                intent=INTENT_CASH_DRAWER,
                ok=True,
                label=f"Caixa esperado — {r['store_label']} — {date_str}",
                data={
                    "date": date_str,
                    "timezone": "America/Sao_Paulo",
                    **{k: v for k, v in r.items() if k != "store"},
                    "nota": (
                        "Saldo ESPERADO pelo sistema. Diferença vs contagem física "
                        "exige conferência/confirmação no Gestor — não altero o caixa."
                    ),
                },
                empty=False,
            )

        return FinanceFacts(
            intent=INTENT_CASH_DRAWER,
            ok=True,
            label=f"Caixa esperado — todas as lojas — {date_str}",
            data={
                "date": date_str,
                "por_loja": [
                    f"{r['store_label']}: R$ {r['saldo_esperado_rs']:.2f}" for r in rows
                ],
                "nota": (
                    "Saldo ESPERADO pelo sistema. Diferença física exige Gestor."
                ),
            },
            empty=False,
        )
    except Exception as exc:
        logger.warning("finance cash drawer query failed: %s", type(exc).__name__)
        return FinanceFacts(intent=INTENT_CASH_DRAWER, ok=False, label="Caixa", error="consulta_falhou")


async def query_low_stock(db, store: Optional[str] = None) -> FinanceFacts:
    try:
        query: Dict[str, Any] = {}
        if store:
            query["store"] = store
        items = await _find(db, "stock", query, {"_id": 0}, 2000)
        low = []
        for item in items:
            qty = item.get("quantity", 0)
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                qty = 0
            min_q = item.get("min_quantity", 5)
            try:
                min_q = int(min_q)
            except (TypeError, ValueError):
                min_q = 5
            # Align with server stock route: low when qty <= min_quantity (fallback 2 historically)
            threshold = min_q if min_q is not None else 2
            if qty <= threshold:
                name = item.get("name") or item.get("item_name") or item.get("menu_item_id") or "?"
                low.append(
                    {
                        "name": name,
                        "quantity": qty,
                        "min_quantity": threshold,
                        "store": item.get("store", ""),
                    }
                )
        low.sort(key=lambda x: x["quantity"])
        lines = [
            f"{i['name']} ({STORE_LABELS.get(i['store'], i['store'])}): {i['quantity']} (mín {i['min_quantity']})"
            for i in low[:20]
        ]
        return FinanceFacts(
            intent=INTENT_LOW_STOCK,
            ok=True,
            label="Estoque baixo",
            data={
                "qtd_itens_baixos": len(low),
                "store_filter": store or "all",
                "itens": lines or ["(nenhum item baixo)"],
            },
            empty=len(low) == 0,
        )
    except Exception as exc:
        logger.warning("finance low stock query failed: %s", type(exc).__name__)
        return FinanceFacts(intent=INTENT_LOW_STOCK, ok=False, label="Estoque baixo", error="consulta_falhou")


async def query_day_summary(db, store: Optional[str] = None) -> FinanceFacts:
    sales = await query_sales_bundle(db, store=store)
    debts = await query_debts(db, store=store)
    prazo = await query_prazo_payments_today(db, store=store)
    stock = await query_low_stock(db, store=store)
    if not sales.ok:
        return FinanceFacts(intent=INTENT_DAY_SUMMARY, ok=False, label="Resumo do dia", error=sales.error)
    data = {
        "date": sales.data.get("date"),
        "timezone": "America/Sao_Paulo",
        "total_vendas_rs": sales.data.get("total_vendas_rs"),
        "pix_rs": sales.data.get("pix_rs"),
        "dinheiro_rs": sales.data.get("dinheiro_rs"),
        "qtd_pedidos": sales.data.get("qtd_pedidos"),
        "manha_total_rs": sales.data.get("manha_total_rs"),
        "tarde_total_rs": sales.data.get("tarde_total_rs"),
        "por_loja_rs": sales.data.get("por_loja_rs"),
        "prazo_aberto_total_rs": debts.data.get("total_prazo_aberto_rs") if debts.ok else None,
        "devedores": debts.data.get("customer_count") if debts.ok else None,
        "prazo_pago_hoje_rs": prazo.data.get("total_rs") if prazo.ok else None,
        "estoque_baixo_itens": stock.data.get("qtd_itens_baixos") if stock.ok else None,
    }
    empty = bool(sales.empty and (not debts.ok or debts.empty) and (not prazo.ok or prazo.empty))
    return FinanceFacts(
        intent=INTENT_DAY_SUMMARY,
        ok=True,
        label=f"Resumo do dia — {sales.data.get('date')}",
        data=data,
        empty=empty,
    )


async def fetch_facts_for_text(text: str, db=None) -> Optional[FinanceFacts]:
    """
    Detect intent and run the matching read-only query.
    Returns None if text is not a known finance intent (caller may still treat as financial stub).
    """
    if _fetcher_override is not None:
        result = _fetcher_override(text)
        if hasattr(result, "__await__"):
            result = await result
        if isinstance(result, FinanceFacts):
            return result
        if isinstance(result, dict):
            return FinanceFacts(
                intent=result.get("intent", INTENT_UNKNOWN_FINANCE),
                ok=bool(result.get("ok", True)),
                label=result.get("label", "dados"),
                data=result.get("data") or {},
                error=result.get("error"),
                empty=bool(result.get("empty", False)),
            )
        return result

    database = db if db is not None else _db
    intent = detect_intent(text)
    if database is None:
        return FinanceFacts(
            intent=intent.intent,
            ok=False,
            label="Financeiro",
            error="db_nao_configurado",
        )

    store = intent.store
    mapping = {
        INTENT_SALES_TODAY: lambda: query_sales_bundle(database, store),
        INTENT_BY_STORE: lambda: query_sales_bundle(database, store),
        INTENT_PIX_TODAY: lambda: query_payment_focus(database, store, "pix", INTENT_PIX_TODAY),
        INTENT_CASH_TODAY: lambda: query_payment_focus(database, store, "cash", INTENT_CASH_TODAY),
        INTENT_DEBTS: lambda: query_debts(database, store),
        INTENT_DEBT_CUSTOMER: lambda: query_debts(database, store, intent.customer_hint),
        INTENT_PRAZO_PAYMENTS_TODAY: lambda: query_prazo_payments_today(database, store),
        INTENT_MORNING_CLOSE: lambda: query_morning_close(database, store),
        INTENT_CASH_DRAWER: lambda: query_cash_drawer(database, store),
        INTENT_LOW_STOCK: lambda: query_low_stock(database, store),
        INTENT_DAY_SUMMARY: lambda: query_day_summary(database, store),
    }
    factory = mapping.get(intent.intent)
    if not factory:
        # Generic financial wording without specific intent — day summary is safest read-only
        return await query_day_summary(database, store)
    return await factory()


__all__ = [
    "IntentResult",
    "FinanceFacts",
    "detect_intent",
    "detect_store",
    "fetch_facts_for_text",
    "set_db",
    "get_db",
    "set_fetcher_override",
    "query_sales_bundle",
    "query_debts",
    "query_low_stock",
    "query_cash_drawer",
    "query_prazo_payments_today",
    "query_morning_close",
    "query_day_summary",
    "brazil_today_bounds",
    "INTENT_SALES_TODAY",
    "INTENT_PIX_TODAY",
    "INTENT_CASH_TODAY",
    "INTENT_DEBTS",
    "INTENT_DEBT_CUSTOMER",
    "INTENT_LOW_STOCK",
    "INTENT_CASH_DRAWER",
    "INTENT_PRAZO_PAYMENTS_TODAY",
    "INTENT_MORNING_CLOSE",
    "INTENT_DAY_SUMMARY",
]

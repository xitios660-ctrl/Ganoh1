"""Transport-neutral synchronization loop for the experimental offline journal.

The caller must provide an authenticated, TLS-protected central endpoint.
No network or MongoDB calls are made by this module. Never point this at the
current legacy /api/orders/sync endpoint, which is not idempotent.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from desktop.offline_store import OfflineJournal, OfflineError


def sync_once(
    journal: OfflineJournal,
    deliver: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    limit: int = 100,
) -> dict[str, int]:
    """Process one batch, preserving UUIDs and pending items after timeouts.

    Responses must match the exact unit, operation UUID and payload fingerprint
    before a central receipt is accepted. A conflict is kept for human review;
    other failures remain pending for a future call.
    """
    stats = {"synced": 0, "conflicts": 0, "retryable": 0}
    for item in journal.pending(limit=limit):
        try:
            response = deliver(item)
        except Exception:
            # A server may have committed even when the response was lost.
            # The same operation_id MUST be used for the next attempt.
            stats["retryable"] += 1
            # Preserve causal order: do not send dependent cash/customer events
            # past an operation whose commit status is still unknown.
            break
        if not isinstance(response, dict) or any(
            response.get(key) != item[key] for key in ("operation_id", "unit", "fingerprint")
        ):
            stats["retryable"] += 1
            # Preserve causal order: do not send dependent cash/customer events
            # past an operation whose commit status is still unknown.
            break
        decision = response.get("status")
        if decision in ("applied", "already_applied"):
            receipt = response.get("receipt_id")
            try:
                journal.acknowledge(item["operation_id"], item["fingerprint"], receipt)
            except OfflineError:
                stats["retryable"] += 1
                break
            stats["synced"] += 1
        elif decision == "conflict":
            reason = response.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                stats["retryable"] += 1
                break
            journal.flag_conflict(item["operation_id"], reason)
            stats["conflicts"] += 1
        else:
            stats["retryable"] += 1
            break
    return stats

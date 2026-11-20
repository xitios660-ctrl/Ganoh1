"""Simulated sync tests: no real network or production state."""
import tempfile
import unittest
from pathlib import Path

from desktop.offline_store import OfflineJournal
from desktop.sync_worker import sync_once


class SimulatedSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "run.sqlite3"
        self.journal = OfflineJournal(self.file, "runner")
        self.saved = self.journal.record_sale(
            sale_id="local-sale-a", total_cents=1290, payment_method="cash",
            items=[{"sku": "sanduiche", "quantity": 1}],
        )

    @staticmethod
    def reply(item, status="applied", **changes):
        return {"operation_id": item["operation_id"], "unit": item["unit"],
                "fingerprint": item["fingerprint"], "status": status,
                "receipt_id": "central-receipt-a", **changes}

    def test_response_lost_after_remote_commit_retry_does_not_duplicate(self):
        """Remote commits once, loses ACK, then returns the same immutable receipt."""
        saved = {}
        calls = []

        def simulated_central(item):
            calls.append(item["operation_id"])
            if item["operation_id"] not in saved:
                saved[item["operation_id"]] = self.reply(item)
                raise ConnectionResetError("server committed, reply lost")
            return {**saved[item["operation_id"]], "status": "already_applied"}

        first = sync_once(self.journal, simulated_central)
        self.assertEqual(first, {"synced": 0, "conflicts": 0, "retryable": 1})
        self.assertEqual(self.journal.status()["pending"], 1)
        restarted = OfflineJournal(self.file, "runner")
        second = sync_once(restarted, simulated_central)
        self.assertEqual(second["synced"], 1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(calls, [self.saved["operation_id"]] * 2)
        self.assertEqual(restarted.status()["synced"], 1)

    def test_wrong_unit_response_does_not_ack(self):
        stats = sync_once(self.journal, lambda item: self.reply(item, unit="gym-londres"))
        self.assertEqual(stats["retryable"], 1)
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_wrong_hash_response_does_not_ack(self):
        stats = sync_once(self.journal, lambda item: self.reply(item, fingerprint="invalid"))
        self.assertEqual(stats["retryable"], 1)
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_conflict_requires_manual_action(self):
        stats = sync_once(
            self.journal,
            lambda item: self.reply(item, status="conflict", reason="stock revision mismatch"),
        )
        self.assertEqual(stats["conflicts"], 1)
        self.assertEqual(self.journal.status()["conflicts"], 1)
        self.assertEqual(sync_once(self.journal, lambda item: self.fail("must not retry"))["synced"], 0)

    def test_no_connection_does_not_lose_operation(self):
        def unavailable(_):
            raise TimeoutError("no Internet")
        self.assertEqual(sync_once(self.journal, unavailable)["retryable"], 1)
        self.assertEqual(OfflineJournal(self.file, "runner").status()["pending"], 1)


if __name__ == "__main__":
    unittest.main()

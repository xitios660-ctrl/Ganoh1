"""Offline journal regression tests. No network, no Atlas, no real business data."""
import tempfile
import unittest
import uuid
from pathlib import Path

from desktop.offline_store import OfflineError, OfflineJournal


class OfflineJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "ganoh.sqlite3"
        self.journal = OfflineJournal(self.path, "runner")

    def sale(self, *, sale_id="test-sale-1", operation_id=None, total_cents=1250,
             payment_method="cash", items=None):
        return self.journal.record_sale(
            sale_id=sale_id,
            total_cents=total_cents,
            payment_method=payment_method,
            items=items if items is not None else [{"sku": "cafe", "quantity": 1}],
            operation_id=operation_id,
        )

    def test_sale_survives_restart_with_same_operation_id(self):
        result = self.sale()
        reopened = OfflineJournal(self.path, "runner")
        batch = reopened.pending()
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0]["operation_id"], result["operation_id"])
        self.assertEqual(batch[0]["payload"]["total_cents"], 1250)
        self.assertEqual(reopened.status()["sqlite_integrity"], "ok")

    def test_retry_same_uuid_and_same_data_is_idempotent(self):
        identifier = str(uuid.uuid4())
        self.assertFalse(self.sale(operation_id=identifier)["already_exists"])
        self.assertTrue(self.sale(operation_id=identifier)["already_exists"])
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_retry_same_uuid_with_different_total_is_rejected(self):
        identifier = str(uuid.uuid4())
        self.sale(operation_id=identifier)
        with self.assertRaises(OfflineError):
            self.sale(operation_id=identifier, total_cents=999999)
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_same_sale_id_another_uuid_rolls_back_both_writes(self):
        self.sale()
        with self.assertRaises(OfflineError):
            self.sale(operation_id=str(uuid.uuid4()))
        self.assertEqual(len(self.journal.pending()), 1)
        self.assertEqual(self.journal.status()["sqlite_integrity"], "ok")

    def test_local_db_cannot_be_opened_by_other_unit(self):
        self.sale()
        with self.assertRaises(OfflineError):
            OfflineJournal(self.path, "gym-londres")
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_wrong_ack_fingerprint_keeps_sale_pending(self):
        result = self.sale()
        with self.assertRaises(OfflineError):
            self.journal.acknowledge(result["operation_id"], "wrong-hash", "central-receipt-1")
        self.assertEqual(self.journal.status()["pending"], 1)

    def test_durable_ack_is_idempotent_and_receipt_is_immutable(self):
        result = self.sale()
        self.journal.acknowledge(result["operation_id"], result["fingerprint"], "receipt-1")
        self.journal.acknowledge(result["operation_id"], result["fingerprint"], "receipt-1")
        self.assertEqual(OfflineJournal(self.path, "runner").status()["synced"], 1)
        with self.assertRaises(OfflineError):
            self.journal.acknowledge(result["operation_id"], result["fingerprint"], "receipt-2")
        self.assertEqual(self.journal.pending(), [])

    def test_conflict_is_retained_for_manual_resolution(self):
        result = self.sale()
        self.journal.flag_conflict(result["operation_id"], "stock version mismatch")
        restarted = OfflineJournal(self.path, "runner")
        self.assertEqual(restarted.status()["conflicts"], 1)
        self.assertEqual(restarted.pending(), [])
        with self.assertRaises(OfflineError):
            restarted.acknowledge(result["operation_id"], result["fingerprint"], "receipt-x")

    def test_invalid_money_and_payment_method_cannot_be_recorded(self):
        for amount in (1.25, "125", True, -1):
            with self.subTest(amount=amount), self.assertRaises(OfflineError):
                self.sale(total_cents=amount)
        with self.assertRaises(OfflineError):
            self.sale(payment_method="unknown")
        with self.assertRaises(OfflineError):
            self.sale(items=[])
        self.assertEqual(self.journal.status()["pending"], 0)

    def test_pending_batches_are_ordered_and_restart_safe(self):
        for index in range(3):
            self.sale(sale_id=f"sale-{index}")
        first = OfflineJournal(self.path, "runner").pending(limit=2)
        self.assertEqual([x["sequence"] for x in first], [1, 2])
        self.assertEqual(self.journal.status()["pending"], 3)


if __name__ == "__main__":
    unittest.main()

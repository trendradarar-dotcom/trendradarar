import os
import tempfile
import unittest

from cryptography.fernet import Fernet

from durable_state import DurableState, DurableStateError


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key().decode()
        self.live = os.path.join(self.tmp.name, "live.sqlite3")
        self.backup = os.path.join(self.tmp.name, "backup.sqlite3")
        self.restored = os.path.join(self.tmp.name, "restored.sqlite3")
        self.store = DurableState(self.live, [self.key])

    def tearDown(self):
        self.tmp.cleanup()

    def _published_record(self):
        self.store.create_publication_intent(
            "idem-pub","a"*64,"acct","DIRECT_POST","b"*64,now=100
        )
        ok, reason = self.store.admit_publication("idem-pub",6,24,2,4,now=101)
        self.assertTrue(ok); self.assertIsNone(reason)
        self.store.transition_publication("idem-pub","SAFETY_APPROVED",now=102)
        self.store.begin_publication_attempt("idem-pub",now=103)
        self.store.transition_publication("idem-pub","PUBLISH_REQUESTED",now=104)
        self.store.transition_publication("idem-pub","UPLOAD_STARTED",now=105,provider_publish_id="provider-1")
        self.store.transition_publication("idem-pub","UPLOADED",now=106)
        self.store.transition_publication("idem-pub","PROCESSING",now=107)
        self.store.transition_publication("idem-pub","PUBLISHED",now=108)

    def test_backup_restore_preserves_publication_and_duplicate_barrier(self):
        self._published_record()
        info = self.store.backup_to(self.backup)
        self.assertEqual(len(info["sha256"]), 64)
        restored = DurableState.restore_backup(self.backup,self.restored,[self.key])
        rec = restored.get_publication("idem-pub")
        self.assertEqual(rec["state"], "PUBLISHED")
        self.assertEqual(rec["provider_publish_id"], "provider-1")
        same, created = restored.create_publication_intent(
            "idem-pub","a"*64,"acct","DIRECT_POST","b"*64,now=200
        )
        self.assertFalse(created)
        self.assertEqual(same["state"], "PUBLISHED")

    def test_processing_record_survives_restart_for_reconciliation(self):
        self.store.create_publication_intent(
            "idem-processing","c"*64,"acct","DIRECT_POST","d"*64,now=300
        )
        ok, _ = self.store.admit_publication("idem-processing",6,24,2,4,now=301)
        self.assertTrue(ok)
        self.store.transition_publication("idem-processing","SAFETY_APPROVED",now=302)
        self.store.begin_publication_attempt("idem-processing",now=303)
        self.store.transition_publication("idem-processing","PUBLISH_REQUESTED",now=304)
        self.store.transition_publication(
            "idem-processing","UPLOAD_STARTED",now=305,provider_publish_id="provider-processing"
        )
        self.store.transition_publication("idem-processing","UPLOADED",now=306)
        self.store.transition_publication("idem-processing","PROCESSING",now=307)
        reopened = DurableState(self.live,[self.key])
        rec = reopened.get_publication("idem-processing")
        self.assertEqual(rec["state"], "PROCESSING")
        self.assertEqual(rec["provider_publish_id"], "provider-processing")
        self.assertEqual(rec["attempt_count"], 1)

    def test_unknown_record_survives_restart_and_cannot_restart_upload(self):
        self.store.create_publication_intent(
            "idem-unknown","e"*64,"acct","DIRECT_POST","f"*64,now=400
        )
        ok, _ = self.store.admit_publication("idem-unknown",6,24,2,4,now=401)
        self.assertTrue(ok)
        self.store.transition_publication("idem-unknown","SAFETY_APPROVED",now=402)
        self.store.begin_publication_attempt("idem-unknown",now=403)
        self.store.transition_publication("idem-unknown","PUBLISH_REQUESTED",now=404)
        self.store.transition_publication(
            "idem-unknown","UPLOAD_STARTED",now=405,provider_publish_id="provider-unknown"
        )
        self.store.transition_publication("idem-unknown","UNKNOWN",now=406,error_code="network_timeout")
        reopened = DurableState(self.live,[self.key])
        rec = reopened.get_publication("idem-unknown")
        self.assertEqual(rec["state"], "UNKNOWN")
        same, created = reopened.create_publication_intent(
            "idem-unknown","e"*64,"acct","DIRECT_POST","f"*64,now=407
        )
        self.assertFalse(created)
        self.assertEqual(same["provider_publish_id"], "provider-unknown")
        with self.assertRaises(DurableStateError):
            reopened.transition_publication("idem-unknown","UPLOAD_STARTED",now=408)

    def test_restore_refuses_overwrite(self):
        self.store.backup_to(self.backup)
        open(self.restored,"wb").close()
        with self.assertRaises(DurableStateError):
            DurableState.restore_backup(self.backup,self.restored,[self.key])


if __name__ == "__main__":
    unittest.main()

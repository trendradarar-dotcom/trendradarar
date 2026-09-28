import os
import tempfile
import unittest

from cryptography.fernet import Fernet

import app
from durable_state import DurableState


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key().decode()
        os.environ["TIKTOK_STATE_DB_PATH"] = os.path.join(self.tmp.name, "state.sqlite3")
        os.environ["TIKTOK_STATE_ENCRYPTION_KEY"] = self.key
        app._STORE = None
        app._STORE_ERROR = ""
        self.store = app.state_store()
        self.old_api = app.api_json_post
        self.now = 1000
        self.sess = {
            "access_token":"a",
            "refresh_token":"r",
            "open_id":"creator",
            "scope":"video.publish,video.upload",
            "expires_at":9999999999,
        }

    def tearDown(self):
        app.api_json_post = self.old_api
        app._STORE = None
        app._STORE_ERROR = ""
        for k in ["TIKTOK_STATE_DB_PATH","TIKTOK_STATE_ENCRYPTION_KEY"]:
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def _record(self, idem, operation, publish_id):
        account_hash = app.fingerprint("creator")
        self.store.create_publication_intent(
            idem,"a"*64,account_hash,operation,"b"*64,now=self.now
        )
        ok, reason = self.store.admit_publication(idem,6,24,4,8,now=self.now+1)
        self.assertTrue(ok); self.assertIsNone(reason)
        self.store.transition_publication(idem,"SAFETY_APPROVED",now=self.now+2)
        self.store.begin_publication_attempt(idem,now=self.now+3)
        self.store.transition_publication(idem,"PUBLISH_REQUESTED",now=self.now+4)
        self.store.transition_publication(
            idem,"UPLOAD_STARTED",now=self.now+5,provider_publish_id=publish_id
        )
        self.store.transition_publication(idem,"UPLOADED",now=self.now+6)
        self.store.transition_publication(idem,"PROCESSING",now=self.now+7)

    def _handler(self, publish_id, sess=None):
        h = app.Handler.__new__(app.Handler)
        h.get_session = lambda: ("sid", sess or self.sess)
        h.js = lambda status, payload, headers=None: (status,payload)
        return h, {"publish_id":[publish_id]}

    def test_direct_publish_complete_becomes_published(self):
        self._record("idem-direct","DIRECT_POST","pub-direct")
        app.api_json_post = lambda url, token, payload=None, timeout=25: (
            200,{"data":{"status":"PUBLISH_COMPLETE"},"error":{"code":"ok"}}
        )
        h,q = self._handler("pub-direct")
        status,_ = h.status_api(q)
        self.assertEqual(status,200)
        self.assertEqual(self.store.get_publication("idem-direct")["state"],"PUBLISHED")

    def test_draft_publish_complete_becomes_ready_not_published(self):
        self._record("idem-draft","DRAFT_UPLOAD","pub-draft")
        app.api_json_post = lambda url, token, payload=None, timeout=25: (
            200,{"data":{"status":"PUBLISH_COMPLETE"},"error":{"code":"ok"}}
        )
        h,q = self._handler("pub-draft")
        status,_ = h.status_api(q)
        self.assertEqual(status,200)
        self.assertEqual(self.store.get_publication("idem-draft")["state"],"READY")

    def test_status_429_becomes_unknown_then_later_success_reconciles(self):
        self._record("idem-429","DIRECT_POST","pub-429")
        responses = [
            (429,{"error":{"code":"rate_limit_exceeded"}}),
            (200,{"data":{"status":"PUBLISH_COMPLETE"},"error":{"code":"ok"}}),
        ]
        app.api_json_post = lambda url, token, payload=None, timeout=25: responses.pop(0)
        h,q = self._handler("pub-429")
        status1,payload1 = h.status_api(q)
        self.assertEqual(status1,429)
        self.assertEqual(payload1["local_state"],"UNKNOWN")
        self.assertEqual(self.store.get_publication("idem-429")["state"],"UNKNOWN")
        status2,payload2 = h.status_api(q)
        self.assertEqual(status2,200)
        self.assertEqual(payload2["local_state"],"PUBLISHED")
        self.assertEqual(self.store.get_publication("idem-429")["state"],"PUBLISHED")

    def test_draft_send_to_user_inbox_becomes_ready(self):
        self._record("idem-draft-inbox","DRAFT_UPLOAD","pub-draft-inbox")
        app.api_json_post = lambda url, token, payload=None, timeout=25: (
            200,{"data":{"status":"SEND_TO_USER_INBOX"},"error":{"code":"ok"}}
        )
        h,q = self._handler("pub-draft-inbox")
        status,payload = h.status_api(q)
        self.assertEqual(status,200)
        self.assertEqual(payload["local_state"],"READY")
        self.assertEqual(self.store.get_publication("idem-draft-inbox")["state"],"READY")

    def test_provider_5xx_becomes_unknown_not_success(self):
        self._record("idem-unknown","DIRECT_POST","pub-unknown")
        app.api_json_post = lambda url, token, payload=None, timeout=25: (
            503,{"error":{"code":"server_error"}}
        )
        h,q = self._handler("pub-unknown")
        status,_ = h.status_api(q)
        self.assertEqual(status,503)
        rec = self.store.get_publication("idem-unknown")
        self.assertEqual(rec["state"],"UNKNOWN")
        self.assertEqual(rec["attempt_count"],1)

    def test_account_mismatch_blocks_reconciliation_before_provider_call(self):
        self._record("idem-account","DIRECT_POST","pub-account")
        called = {"value":False}
        def api(*args, **kwargs):
            called["value"]=True
            return 200,{"data":{"status":"PUBLISH_COMPLETE"},"error":{"code":"ok"}}
        app.api_json_post = api
        wrong = dict(self.sess)
        wrong["open_id"]="different-creator"
        h,q = self._handler("pub-account",wrong)
        status,payload = h.status_api(q)
        self.assertEqual(status,403)
        self.assertEqual(payload["error"],"publication_account_mismatch")
        self.assertFalse(called["value"])
        self.assertEqual(self.store.get_publication("idem-account")["state"],"PROCESSING")


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import threading
import unittest

from cryptography.fernet import Fernet

from durable_state import DurableState


class AtomicityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key().decode()
        self.db = os.path.join(self.tmp.name, "state.sqlite3")
        self.store = DurableState(self.db, [self.key])

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_publication_intent_has_single_creator(self):
        barrier = threading.Barrier(8)
        results = []
        errors = []
        lock = threading.Lock()

        def worker():
            try:
                barrier.wait()
                rec, created = self.store.create_publication_intent(
                    "same-idem","a"*64,"acct","DIRECT_POST","b"*64
                )
                with lock:
                    results.append((created, rec["idempotency_key"]))
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 8)
        self.assertEqual(sum(1 for created,_ in results if created), 1)
        self.assertTrue(all(key == "same-idem" for _,key in results))

    def test_active_account_limit_has_single_admission_under_race(self):
        for idem, content in (("idem-a","c"*64),("idem-b","d"*64)):
            self.store.create_publication_intent(
                idem,content,"same-account","DIRECT_POST","e"*64
            )

        barrier = threading.Barrier(2)
        results = {}
        errors = []
        lock = threading.Lock()

        def worker(idem):
            try:
                barrier.wait()
                outcome = self.store.admit_publication(
                    idem,6,24,1,2,12,48
                )
                with lock:
                    results[idem] = outcome
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))

        threads = [threading.Thread(target=worker,args=(idem,)) for idem in ("idem-a","idem-b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        allowed = [idem for idem,(ok,_) in results.items() if ok]
        blocked = [(idem,reason) for idem,(ok,reason) in results.items() if not ok]
        self.assertEqual(len(allowed), 1)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0][1], "active_account_limit")


if __name__ == "__main__":
    unittest.main()

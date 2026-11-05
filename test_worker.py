"""Queue coverage and cache behavior for visible transcript rows."""
from collections import OrderedDict
from concurrent.futures import Future
from queue import SimpleQueue
from threading import Event, Lock
import unittest
from unittest.mock import patch

from speech import Speech
from transcript import CaptionRequest
from worker import CaptionWorker
import screen


class CaptionWorkerTest(unittest.TestCase):
    def make_worker(self) -> CaptionWorker:
        return CaptionWorker(screen.Region(0, 0, 600, 200), Event(), SimpleQueue(),
                             Lock(), True, False)

    def test_all_visible_rows_remain_queued(self) -> None:
        worker = self.make_worker()
        requests = [CaptionRequest(index, Speech("alex", f"Sentence {index}."), 1.0)
                    for index in range(8)]
        with patch.object(worker.buffer, "take", return_value=requests):
            worker.enqueue()
        self.assertEqual(list(worker.waiting.values()), requests)

    def test_cached_revision_removes_older_queued_preview(self) -> None:
        worker = self.make_worker()
        first = CaptionRequest(0, Speech("alex", "We need"), 1.0)
        final = CaptionRequest(0, Speech("alex", "We need to update."), 2.0)
        worker.waiting = OrderedDict(((0, first),))
        worker.cache[final.speech] = "업데이트해야 합니다."
        with patch.object(worker.buffer, "take", return_value=[final]):
            worker.enqueue()
        self.assertFalse(worker.waiting)
        worker.events.get_nowait()
        kind, value = worker.events.get_nowait()
        self.assertEqual(kind, "caption")
        self.assertEqual(value, (final, "업데이트해야 합니다.", 0))

    def test_completed_job_keeps_its_own_request_and_records_translation(self) -> None:
        worker = self.make_worker()
        request = CaptionRequest(3, Speech("sam", "Hello."), 1.0)
        worker.request = request
        worker.future = Future()
        worker.future.set_result((Speech("sam", "안녕하세요."), 120))
        worker.receive()
        self.assertEqual(worker.events.get_nowait(), ("caption", (request, "안녕하세요.", 120)))
        self.assertEqual(worker.cache[request.speech], "안녕하세요.")
        self.assertIsNone(worker.future)


if __name__ == "__main__":
    unittest.main()

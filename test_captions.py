"""Regression tests for rolling OCR snapshots."""
import unittest

from captions import SentenceBuffer


class SentenceBufferTest(unittest.TestCase):
    def test_joins_overlapping_and_nonoverlapping_fragments(self) -> None:
        captions = SentenceBuffer()
        captions.observe("Please check the", 1.0)
        self.assertIsNone(captions.take(1.4))
        captions.observe("check the camera", 1.5)
        captions.observe("calibration before the meeting.", 2.0)
        self.assertEqual(
            captions.take(2.4), "Please check the camera calibration before the meeting."
        )

    def test_replaces_a_revised_tail(self) -> None:
        captions = SentenceBuffer()
        captions.observe("Please turn left.", 1.0)
        captions.observe("Please turn right.", 1.1)
        self.assertIsNone(captions.take(1.2))
        self.assertEqual(captions.take(1.4), "Please turn right.")

    def test_commits_a_sentence_while_the_next_sentence_grows(self) -> None:
        captions = SentenceBuffer()
        captions.observe("It works. Next", 1.0)
        captions.observe("It works. Next we", 1.1)
        captions.observe("It works. Next we test", 1.2)
        self.assertEqual(captions.take(1.3), "It works.")
        captions.observe("Next we test it.", 1.4)
        self.assertEqual(captions.take(1.7), "Next we test it.")
        self.assertIsNone(captions.take(2.0))

    def test_quiet_preview_preserves_the_sentence_for_completion(self) -> None:
        captions = SentenceBuffer()
        captions.observe("Please ask Dr. Lee to", 1.0)
        self.assertIsNone(captions.take(1.5))
        self.assertEqual(captions.take(3.0), "Please ask Dr. Lee to")
        self.assertIsNone(captions.take(3.1))
        captions.observe("Lee to join the call.", 3.2)
        self.assertEqual(captions.take(3.5), "Please ask Dr. Lee to join the call.")

    def test_silence_flushes_and_allows_the_same_sentence_again(self) -> None:
        captions = SentenceBuffer()
        captions.observe("Next slide please", 1.0)
        captions.observe("", 1.4)
        self.assertEqual(captions.take(3.0), "Next slide please")
        self.assertEqual(captions.take(4.0), "")
        captions.observe("Next slide please", 4.5)
        self.assertEqual(captions.take(6.5), "Next slide please")

    def test_new_sentence_can_start_with_the_same_words(self) -> None:
        captions = SentenceBuffer()
        captions.observe("We can start.", 1.0)
        self.assertEqual(captions.take(1.3), "We can start.")
        captions.observe("We can finish.", 1.5)
        self.assertEqual(captions.take(1.8), "We can finish.")

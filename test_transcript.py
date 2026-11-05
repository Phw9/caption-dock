"""Live transcript ordering, preview updates, and bounded display history."""
import unittest

from speech import Speech
from transcript import (CaptionRequest, MAX_TRANSCRIPT_ROWS, TranscriptBuffer,
                        TranscriptHistory)


class TranscriptBufferTest(unittest.TestCase):
    def test_new_sentence_can_start_with_same_words_as_finished_sentence(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "We can start.")], 1.0)
        buffer.take(1.4)
        buffer.observe([Speech("alex", "We can finish.")], 1.5)
        self.assertEqual([item.speech.text for item in buffer.take(1.9)], ["We can finish."])

    def test_silence_allows_same_sentence_again_with_a_new_identifier(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "Next slide please")], 1.0)
        buffer.observe([], 1.4)
        first = buffer.take(3.0)
        buffer.observe([Speech("alex", "Next slide please")], 4.5)
        second = buffer.take(6.5)
        self.assertEqual(first[0].speech, second[0].speech)
        self.assertNotEqual(first[0].identifier, second[0].identifier)

    def test_all_visible_sentences_are_emitted_together(self) -> None:
        buffer = TranscriptBuffer()
        sentences = ["First sentence.", "Second sentence.", "Third sentence.",
                     "Fourth sentence.", "Fifth sentence.", "Sixth sentence."]
        buffer.observe([Speech("alex", text) for text in sentences], 1.0)
        self.assertEqual(buffer.take(1.1), [])
        items = buffer.take(1.4)
        self.assertEqual([item.speech.text for item in items], sentences)
        self.assertEqual(len({item.identifier for item in items}), 6)
        self.assertEqual(buffer.take(2.0), [])

    def test_same_speaker_returning_stays_in_screen_order(self) -> None:
        buffer = TranscriptBuffer()
        speech = [Speech("alex", "Please check."), Speech("sam", "I will check."),
                  Speech("alex", "Thank you.")]
        buffer.observe(speech, 1.0)
        self.assertEqual([item.speech for item in buffer.take(1.4)], speech)

    def test_rolling_caption_is_assembled_before_translation(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "We need to update the")], 1.0)
        self.assertEqual(buffer.take(1.5), [])
        buffer.observe([Speech("alex", "update the camera calibration.")], 1.6)
        items = buffer.take(2.0)
        self.assertEqual([item.speech.text for item in items],
                         ["We need to update the camera calibration."])

    def test_preview_and_completed_sentence_have_one_identifier(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "We need to update")], 1.0)
        first = buffer.take(3.0)
        buffer.observe([Speech("alex", "We need to update the camera.")], 3.1)
        final = buffer.take(3.5)
        self.assertEqual(first[0].identifier, final[0].identifier)
        self.assertEqual(final[0].speech.text, "We need to update the camera.")

    def test_top_scroll_does_not_retranslate_already_committed_sentences(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "Please check the camera. We need to update the")], 1.0)
        first = buffer.take(1.4)
        self.assertEqual([item.speech.text for item in first], ["Please check the camera."])
        buffer.observe([Speech("alex", "camera. We need to update the camera calibration.")], 1.5)
        second = buffer.take(1.9)
        self.assertEqual([item.speech.text for item in second],
                         ["We need to update the camera calibration."])

    def test_speaker_change_closes_incomplete_sentence_without_mixing_people(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "Please check the build"),
                        Speech("sam", "I will check it.")], 1.0)
        self.assertEqual([item.speech for item in buffer.take(1.4)], [
            Speech("alex", "Please check the build"), Speech("sam", "I will check it.")
        ])

    def test_more_than_old_word_limit_is_preserved(self) -> None:
        buffer = TranscriptBuffer()
        sentences = [f"Please check camera number {index}." for index in range(24)]
        buffer.observe([Speech("alex", " ".join(sentences))], 1.0)
        self.assertEqual([item.speech.text for item in buffer.take(1.4)], sentences)

    def test_live_latest_words_do_not_delay_earlier_complete_rows(self) -> None:
        buffer = TranscriptBuffer()
        buffer.observe([Speech("alex", "The build passed. We need")], 1.0)
        buffer.observe([Speech("alex", "The build passed. We need to update")], 1.2)
        self.assertEqual([item.speech.text for item in buffer.take(1.4)], ["The build passed."])


class TranscriptHistoryTest(unittest.TestCase):
    def test_preview_is_replaced_and_stale_result_is_ignored(self) -> None:
        history = TranscriptHistory()
        first = CaptionRequest(0, Speech("alex", "We need"), 1.0)
        final = CaptionRequest(0, Speech("alex", "We need to update."), 2.0)
        history.pending(first)
        history.pending(final)
        self.assertFalse(history.translated(first, "오래된 번역"))
        self.assertTrue(history.translated(final, "업데이트해야 합니다."))
        self.assertEqual(len(history.rows), 1)
        self.assertEqual(history.rows[0].translated, "업데이트해야 합니다.")

    def test_clear_ignores_results_from_old_inflight_jobs(self) -> None:
        history = TranscriptHistory()
        request = CaptionRequest(0, Speech("alex", "Hello."), 1.0)
        history.pending(request)
        history.clear()
        self.assertFalse(history.translated(request, "안녕하세요."))
        self.assertEqual(len(history.rows), 0)

    def test_translation_results_keep_initial_row_order_and_bound_memory(self) -> None:
        history = TranscriptHistory()
        for index in range(MAX_TRANSCRIPT_ROWS + 10):
            request = CaptionRequest(index, Speech("alex", f"Sentence {index}."), 1.0)
            history.pending(request)
        self.assertEqual(len(history.rows), MAX_TRANSCRIPT_ROWS)
        self.assertEqual(next(iter(history.rows)), 10)


if __name__ == "__main__":
    unittest.main()

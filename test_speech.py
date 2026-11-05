"""Regression cases for Teams name rows and wrapped caption text."""
import unittest

from speech import CaptionLine, Speech, SpeechBuffer, read_tsv, split_speech
from speech import translate_speech


def team_rows(name: str, *text: str) -> list[CaptionLine]:
    lines = [CaptionLine(name, 0, 13)]
    lines.extend(CaptionLine(line, 35 + index * 28, 22) for index, line in enumerate(text))
    return lines


class TeamsCaptionTest(unittest.TestCase):
    def test_compact_repeated_account_rows_are_not_speech(self) -> None:
        lines = [
            CaptionLine("alex@example.com", 0, 12),
            CaptionLine("We need to update the", 18, 18),
            CaptionLine("alex@example.com", 42, 12),
            CaptionLine("camera calibration.", 60, 18),
        ]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "We need to update the camera calibration.")
        ])

    def test_cropped_top_row_keeps_previous_speaker(self) -> None:
        lines = [
            CaptionLine("update the camera", 0, 18),
            CaptionLine("alex@example.com", 25, 12),
            CaptionLine("calibration before the release.", 43, 18),
        ]
        self.assertEqual(split_speech(lines, True, "alex@example.com"), [
            Speech("alex@example.com", "update the camera calibration before the release.")
        ])

    def test_caption_before_first_known_account_is_not_a_speaker(self) -> None:
        lines = [
            CaptionLine("old clipped words.", 0, 12),
            CaptionLine("alex@example.com", 25, 12),
            CaptionLine("Please check the camera.", 43, 18),
        ]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "Please check the camera.")
        ])

    def test_header_is_separate_and_wrapped_words_stay_together(self) -> None:
        speech = split_speech(team_rows("alex.kim", "We need to update the", "camera calibration."), True)
        self.assertEqual(speech, [Speech("alex.kim", "We need to update the camera calibration.")])

    def test_name_alone_is_never_translated(self) -> None:
        buffer = SpeechBuffer()
        buffer.observe(split_speech(team_rows("alex.kim"), True), 1.0)
        self.assertEqual(buffer.take(10.0), [])

    def test_repeated_name_does_not_replace_a_rolling_sentence(self) -> None:
        buffer = SpeechBuffer()
        buffer.observe(split_speech(team_rows("Alex Kim", "We need to update the"), True), 1.0)
        buffer.observe(split_speech(team_rows("Alex Kim", "update the camera calibration."), True), 1.4)
        self.assertEqual(buffer.take(1.8), [Speech("Alex Kim", "We need to update the camera calibration.")])

    def test_speaker_change_does_not_combine_two_people(self) -> None:
        buffer = SpeechBuffer()
        buffer.observe([Speech("Alex Kim", "Please check the build")], 1.0)
        buffer.observe([Speech("Sam Lee", "I will check it.")], 1.2)
        self.assertEqual(buffer.take(1.3), [Speech("Alex Kim", "Please check the build")])
        self.assertEqual(buffer.take(1.6), [Speech("Sam Lee", "I will check it.")])

    def test_two_speaker_blocks_are_separate(self) -> None:
        lines = team_rows("Alex Kim", "Please check the build.")
        lines.extend([CaptionLine("Sam Lee", 90, 13), CaptionLine("I will check it.", 125, 22)])
        self.assertEqual(split_speech(lines, True), [
            Speech("Alex Kim", "Please check the build."),
            Speech("Sam Lee", "I will check it."),
        ])

    def test_generic_mode_keeps_all_rows_as_speech(self) -> None:
        lines = [CaptionLine("The meeting", 0, 22), CaptionLine("starts at five.", 28, 22)]
        self.assertEqual(split_speech(lines, False), [Speech("", "The meeting starts at five.")])

    def test_translation_receives_body_only_and_preserves_name_row(self) -> None:
        inputs = []

        def translate(text: str) -> str:
            inputs.append(text)
            return "카메라를 점검해 주세요."

        result = translate_speech(Speech("alex.kim", "Please check the camera."), translate)
        self.assertEqual(inputs, ["Please check the camera."])
        self.assertEqual(result, "alex.kim\n카메라를 점검해 주세요.")

    def test_tsv_keeps_two_rows_even_with_a_low_confidence_name(self) -> None:
        header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        tsv = header + (
            "5\t1\t1\t1\t1\t1\t0\t0\t80\t13\t12\talex.kim\n"
            "5\t1\t1\t1\t2\t1\t0\t35\t60\t22\t95\tPlease\n"
            "5\t1\t1\t1\t2\t2\t70\t35\t60\t22\t96\tcheck.\n"
        )
        lines = read_tsv(tsv)
        self.assertEqual([line.text for line in lines], ["alex.kim", "Please check."])
        self.assertEqual(split_speech(lines, True), [Speech("alex.kim", "Please check.")])
        self.assertEqual(read_tsv(tsv[len(header):]), lines)

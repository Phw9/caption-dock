"""Regression cases for Teams name rows and wrapped caption text."""
import unittest

from speech import CaptionLine, CaptionWord, Speech, SpeechBuffer, read_tsv, split_speech
from speech import account_column, speaker_label, translate_caption, translate_speech


def team_rows(name: str, *text: str) -> list[CaptionLine]:
    lines = [CaptionLine(name, 0, 13)]
    lines.extend(CaptionLine(line, 35 + index * 28, 22) for index, line in enumerate(text))
    return lines


class TeamsCaptionTest(unittest.TestCase):
    def test_distant_close_button_is_not_a_caption_word(self) -> None:
        lines = [CaptionLine("alex@example.com x", 0, 20, 20, 90, (
            CaptionWord("alex@example.com", 0, 14, 20, 90, 160),
            CaptionWord("x", 0, 20, 700, 90, 15),
        )), CaptionLine("Please check X", 22, 20, 20, 95, (
            CaptionWord("Please", 22, 20, 20, 95, 60),
            CaptionWord("check", 22, 20, 90, 95, 60),
            CaptionWord("X", 22, 20, 160, 95, 15),
        ))]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "Please check X")
        ])

    def test_avatar_tokens_are_removed_from_account_and_body_rows(self) -> None:
        lines = [
            CaptionLine("spay alex@example.com", 0, 26, 12, 45, (
                CaptionWord("spay", 11, 15, 12, 42),
                CaptionWord("alex@example.com", 0, 12, 63, 75),
            )),
            CaptionLine("tm Please check the camera.", 20, 20, 31, 90, (
                CaptionWord("tm", 24, 5, 31, 50),
                CaptionWord("Please", 20, 20, 63, 95),
                CaptionWord("check", 20, 20, 125, 95),
                CaptionWord("the", 20, 20, 180, 95),
                CaptionWord("camera.", 20, 20, 220, 95),
            )),
        ]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "Please check the camera.")
        ])
        damaged = CaptionLine("spay alex@examplecom", 0, 26, 12, 45, (
            CaptionWord("spay", 11, 15, 12, 15),
            CaptionWord("alex@examplecom", 0, 12, 63, 75),
        ))
        self.assertEqual(account_column(damaged), 63)
        self.assertEqual(split_speech([damaged, lines[1]], True), [
            Speech("", "Please check the camera.")
        ])

    def test_first_caption_word_is_not_assumed_to_be_a_name(self) -> None:
        lines = [CaptionLine("spay", 0, 20), CaptionLine("Please check the camera.", 25, 20)]
        self.assertEqual(split_speech(lines, True), [
            Speech("", "spay Please check the camera.")
        ])

    def test_short_word_with_smaller_glyphs_is_not_a_new_speaker(self) -> None:
        lines = [CaptionLine("alex@example.com", 0, 14),
                 CaptionLine("Please check the camera.", 20, 20),
                 CaptionLine("Zero", 45, 14)]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "Please check the camera. Zero")
        ])
        self.assertEqual(split_speech(lines[-1:], True, "alex@example.com"), [
            Speech("alex@example.com", "Zero")
        ])

    def test_body_only_keeps_previous_speaker_and_first_line(self) -> None:
        lines = [CaptionLine("We need to update the", 0, 20),
                 CaptionLine("camera calibration.", 25, 20)]
        self.assertEqual(split_speech(lines, True, "Alex Kim"), [
            Speech("Alex Kim", "We need to update the camera calibration.")
        ])

    def test_malformed_account_is_excluded_and_matches_known_speaker(self) -> None:
        lines = [CaptionLine("alex@example.com", 0, 12),
                 CaptionLine("We need to update the", 18, 20),
                 CaptionLine("alex@examplecom", 44, 12),
                 CaptionLine("camera calibration.", 62, 20)]
        self.assertEqual(split_speech(lines, True), [
            Speech("alex@example.com", "We need to update the camera calibration.")
        ])

    def test_unrecognized_account_never_becomes_translated_body(self) -> None:
        lines = [CaptionLine("unknown@gmaicom", 0, 12),
                 CaptionLine("Please check the camera.", 18, 20)]
        self.assertEqual(split_speech(lines, True), [Speech("", "Please check the camera.")])

    def test_email_mentioned_in_sentence_is_body_text(self) -> None:
        lines = team_rows("Alex Kim", "Please send it to alex@example.com.")
        self.assertEqual(split_speech(lines, True), [
            Speech("Alex Kim", "Please send it to alex@example.com.")
        ])
        mention = CaptionLine("Email alex@example.com", 0, 20, 10, 95, (
            CaptionWord("Email", 0, 20, 10, 95),
            CaptionWord("alex@example.com", 0, 20, 80, 95),
        ))
        self.assertIsNone(account_column(mention))

    def test_translated_caption_keeps_speaker_out_of_translation_text(self) -> None:
        result = translate_caption(Speech("alex@example.com", "Hello."), lambda _: "안녕하세요.")
        self.assertEqual(result, Speech("alex@example.com", "안녕하세요."))
        self.assertEqual(speaker_label(result.speaker), "alex")

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

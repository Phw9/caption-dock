"""Local OCR, caption stabilization, and CPU translation."""
import ctypes
import re
from pathlib import Path

import ctranslate2
import numpy as np
import sentencepiece

MAX_SOURCE_TOKENS = 180


class Translator:
    def __init__(self, model: Path) -> None:
        self.source = sentencepiece.SentencePieceProcessor(
            model_proto=(model / "source.spm").read_bytes()
        )
        self.target = sentencepiece.SentencePieceProcessor(
            model_proto=(model / "target.spm").read_bytes()
        )
        self.engine = ctranslate2.Translator(
            str(model), device="cpu", compute_type="int8",
            inter_threads=1, intra_threads=1,
        )

    def translate(self, text: str) -> str:
        tokens = self.source.encode(text, out_type=str)[-MAX_SOURCE_TOKENS:]
        result = self.engine.translate_batch(
            [tokens], beam_size=2, max_decoding_length=160,
        )[0].hypotheses[0]
        translated = self.target.decode(result)
        return translated.strip()


class Ocr:
    def __init__(self, assets: Path) -> None:
        # The binary is built without Tesseract's optional archive and HTTP readers.
        self.library = ctypes.CDLL(str(assets / "tesseract.dll"))
        handle, integer = ctypes.c_void_p, ctypes.c_int
        self.create = self.bind("TessBaseAPICreate", handle)
        self.delete = self.bind("TessBaseAPIDelete", None, handle)
        init = self.bind(
            "TessBaseAPIInit5", integer, handle, ctypes.c_char_p, integer,
            ctypes.c_char_p, integer, handle, integer, handle, handle,
            ctypes.c_size_t, integer,
        )
        set_mode = self.bind("TessBaseAPISetPageSegMode", None, handle, integer)
        self.set_image = self.bind("TessBaseAPISetImage", None, handle,
                                   ctypes.c_char_p, integer, integer,
                                   integer, integer)
        self.get_text = self.bind("TessBaseAPIGetUTF8Text", handle, handle)
        self.delete_text = self.bind("TessDeleteText", None, handle)
        self.confidence = self.bind("TessBaseAPIMeanTextConf", integer, handle)
        self.clear = self.bind("TessBaseAPIClear", None, handle)
        model = (assets / "tessdata" / "eng.traineddata").read_bytes()
        self.api = self.create()
        if not self.api:
            raise RuntimeError("Could not create an OCR engine.")
        lstm_only, single_block = 1, 6
        if init(self.api, model, len(model), b"eng", lstm_only,
                None, 0, None, None, 0, 0):
            self.delete(self.api)
            raise RuntimeError("Could not initialize the English OCR model.")
        set_mode(self.api, single_block)

    def bind(self, name, result, *args):
        function = getattr(self.library, name)
        function.restype = result
        function.argtypes = args
        return function

    def __enter__(self) -> "Ocr":
        return self

    def __exit__(self, *_exc) -> None:
        self.delete(self.api)

    def read(self, image: np.ndarray) -> str:
        # Convert BGR to luminance with integer BT.601 weights scaled to 256.
        blue, green, red = image.astype(np.uint16).transpose(2, 0, 1)
        gray = ((29 * blue + 150 * green + 77 * red) >> 8).astype(np.uint8)
        height, width = gray.shape
        scale = min(1.0, 1400 / width, 600 / height)
        if scale < 1:
            rows = np.linspace(0, height - 1, int(height * scale), dtype=int)
            cols = np.linspace(0, width - 1, int(width * scale), dtype=int)
            gray = gray[np.ix_(rows, cols)]
        if gray.mean() < 120:
            gray = 255 - gray
        if gray.shape[0] < 180 and gray.shape[1] <= 900:
            gray = gray.repeat(2, axis=0).repeat(2, axis=1)
        low, high = int(gray.min()), int(gray.max())
        text = ""
        if high - low >= 16:
            gray = ((gray.astype(np.uint16) - low) * 255 // (high - low)).astype(
                np.uint8
            )
            text = self.recognize(np.pad(gray, 12, constant_values=255))
        return text

    def recognize(self, gray: np.ndarray) -> str:
        height, width = gray.shape
        pixels = gray.tobytes()
        self.set_image(self.api, pixels, width, height, 1, width)
        output = self.get_text(self.api)
        text = ""
        try:
            if output and self.confidence(self.api) >= 35:
                text = ctypes.string_at(output).decode("utf-8")
        finally:
            if output:
                self.delete_text(output)
            self.clear(self.api)
        normalized = re.sub(r"\s+", " ", text).strip()
        if not re.search(r"[A-Za-z]", normalized):
            normalized = ""
        return normalized

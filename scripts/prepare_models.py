"""Fetch the pinned upstream weights and convert the translation model to INT8."""
import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen
from zipfile import ZipFile

MODEL_URL = (
    "https://object.pouta.csc.fi/Tatoeba-MT-models/eng-kor/"
    "opusTCv20210807-sepvoc_transformer-big_2022-07-28.zip"
)
MODEL_SHA256 = "41f771fa28e864428dd7589992867b2b6dfa402f1191670e818e019dddfceef7"
MODEL_STEM = "opusTCv20210807-sepvoc.spm32k-spm32k"
WEIGHTS = f"{MODEL_STEM}.transformer-big.model1.npz.best-perplexity.npz"
OCR_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/"
    "eng.traineddata"
)
OCR_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return digest


def fetch(url: str, target: Path, digest: str) -> None:
    if not target.exists() or sha256(target) != digest:
        temporary = target.with_suffix(target.suffix + ".part")
        with urlopen(url, timeout=120) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
        if sha256(temporary) != digest:
            raise ValueError(f"SHA-256 mismatch for {target.name}.")
        temporary.replace(target)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    upstream = root / "build" / "opus-source"
    assets = root / "assets"
    tessdata = assets / "tessdata"
    upstream.mkdir(parents=True, exist_ok=True)
    tessdata.mkdir(parents=True, exist_ok=True)
    archive = upstream.parent / "opus-marian.zip"
    fetch(MODEL_URL, archive, MODEL_SHA256)
    fetch(OCR_URL, tessdata / "eng.traineddata", OCR_SHA256)
    from ctranslate2.converters import MarianConverter

    vocabularies = []
    with ZipFile(archive) as source:
        for filename in (WEIGHTS, "source.spm", "target.spm"):
            with source.open(filename) as data, (upstream / filename).open("wb") as out:
                shutil.copyfileobj(data, out, length=1024 * 1024)
        for side in ("src", "trg"):
            vocabulary = upstream / f"{side}.yml"
            tokens = source.read(f"{MODEL_STEM}.{side}.vocab").decode("utf-8").split("\n")
            # This OPUS archive uses line numbers as token IDs. The converter
            # accepts Marian YAML vocabularies, so keep those IDs explicitly.
            with vocabulary.open("w", encoding="utf-8") as out:
                for index, token in enumerate(tokens):
                    if token:
                        quoted = token.replace("'", "''")
                        out.write(f"'{quoted}': {index}\n")
            vocabularies.append(str(vocabulary))
    converter = MarianConverter(str(upstream / WEIGHTS), vocabularies)
    converter.convert(str(assets / "opus"), quantization="int8", force=True)
    for filename in ("source.spm", "target.spm"):
        shutil.copyfile(upstream / filename, assets / "opus" / filename)


if __name__ == "__main__":
    main()

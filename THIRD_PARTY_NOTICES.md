# Third-party notices

Caption Dock's original application code is MIT licensed. The embedded components
and models retain their respective licenses. The release includes the applicable
license and notice texts.

| Component | License and source |
| --- | --- |
| OPUS-MT English → Korean | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Model and SentencePiece data by Helsinki-NLP and OPUS-MT contributors. [Model card](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-ko) and [original Marian checkpoint](https://object.pouta.csc.fi/Tatoeba-MT-models/eng-kor/opusTCv20210807-sepvoc_transformer-big_2022-07-28.zip). Caption Dock converts the original neural weights and separate vocabularies to CTranslate2 INT8. The SentencePiece files are unchanged. |
| CTranslate2 4.6.0 | [MIT](https://github.com/OpenNMT/CTranslate2/blob/v4.6.0/LICENSE). The release pairs the upstream Python binding with the same revision of the CPU library, built with Ruy. |
| CTranslate2 native dependencies | [Ruy](https://github.com/google/ruy/blob/363f252289fb7a1fba1703d99196524698cb884d/LICENSE) and [cpu_features](https://github.com/google/cpu_features/blob/8a494eb1e158ec2050e5f699a504fbc9b896a43b/LICENSE) (Apache 2.0), [cpuinfo](https://github.com/pytorch/cpuinfo/blob/082deffc80ce517f81dc2f3aebe6ba671fcd09c9/LICENSE) (BSD 2-Clause), [spdlog](https://github.com/gabime/spdlog/blob/76fb40d95455f249bd70824ecfcae7a8f0930fa3/LICENSE) (MIT) and its bundled [fmt](https://fmt.dev/latest/license/) (MIT with exception). |
| Additional CTranslate2 dependencies | [BS::thread_pool](https://github.com/bshoshany/thread-pool/tree/v3.5.0), half-float and nlohmann/json (MIT), clog (BSD 2-Clause), pybind11 (BSD 3-Clause). |
| Tesseract 5.5.1 and English traineddata 4.1.0 | Apache 2.0. [Engine](https://github.com/tesseract-ocr/tesseract/tree/5.5.1) and [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0). |
| Leptonica 1.87.0 | [BSD 2-Clause](https://github.com/DanBloomberg/leptonica/blob/1.87.0/leptonica-license.txt). Statically linked by Tesseract. |
| SentencePiece 0.2.1 | [Apache 2.0](https://github.com/google/sentencepiece/blob/v0.2.1/LICENSE). |
| Python, Tcl/Tk | [PSF and bundled licenses](https://docs.python.org/3.12/license.html), [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html). |
| NumPy, PyYAML, setuptools, packaging | See the installed distributions' license files. The NumPy wheel includes additional OpenBLAS notices. |
| PyInstaller 6.20.0 | [GPL 2.0 or later with bootloader exception](https://pyinstaller.org/en/stable/license.html). The exception permits distribution of the bundled application under its own license. |
| Microsoft Visual C++ runtime | Redistributable components from the Windows Python distribution and the Visual Studio C++ toolchain. [Microsoft redistribution terms](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files). |

[LingoLens](https://github.com/amantu-qbit/LingoLens) and [MORT](https://github.com/kmonkeyhead/MORT)
were reviewed as MIT-licensed references for screen region selection, OCR, and
change detection. Caption Dock implements these features independently.

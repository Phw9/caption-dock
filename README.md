# Caption Dock

Windows 11에서 화면의 영어 자막을 읽어 한국어로 번역하고, 화면 위에 표시합니다.
Teams의 영어 실시간 자막을 켠 뒤 번역할 영역을 드래그하면 됩니다. 번역과 OCR은
CPU에서 실행되며 모델은 실행파일에 포함되어 있습니다.

1. [릴리스](https://github.com/Phw9/caption-dock/releases/latest)에서
   `caption-dock-v0.1.0-portable.exe`를 내려받아 실행합니다.
2. Teams에서 영어 자막을 켭니다. 앱의 **Select area**를 누르고 영어 자막 줄만
   드래그합니다. **Esc**로 선택을 취소할 수 있습니다.
3. **Cover the English captions**를 끄면 번역을 자막 근처에 표시합니다.
   **Pause**를 누르면 처리를 멈춥니다. Teams 창을 움직인 뒤에는 영역을 다시
   선택합니다.

앱은 선택한 영역의 픽셀, OCR 결과, 번역문을 메모리에서 처리합니다. 자막 기록,
원격 번역, 자동 업데이트 기능은 없습니다. 실행 시 내장 런타임과 모델을 Windows
임시 폴더에 풀고 정상 종료 시 정리합니다. 캡처 제외를 설정할 수 없는 환경에서는
영어 자막을 덮는 모드를 비활성화합니다. 보안 정책으로 캡처가 차단된 화면은 읽을
수 없습니다.

Windows 11 x64용입니다. 첫 릴리스는 서명되지 않았습니다. 회사 PC에서 실행할
때는 조직의 앱 실행 정책을 따르세요. 모델의 출처와 라이선스는
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.

## Build and verify

Use Windows x64, Python 3.12, Visual Studio 2026 C++ Desktop tools, CMake 4.2+,
Git, and PowerShell 7. Model preparation needs internet access and a separate
Python environment. Runtime needs no download.

```powershell
py -3.12 -m venv build/convert-env
build/convert-env/Scripts/python -m pip install ctranslate2==4.6.0 numpy==2.5.4 PyYAML==6.0.3 setuptools==80.9.0
build/convert-env/Scripts/python scripts/prepare_models.py

pwsh -File scripts/build-native.ps1
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-build.txt
pwsh -File scripts/package.ps1
```

Run the packaged smoke test from an unlocked desktop. It opens a synthetic
caption and overlay briefly and records results for that synthetic input.

```powershell
Start-Process -Wait -FilePath ./dist/caption-dock-v0.1.0-portable.exe -ArgumentList '--self-test build/report.json'
Get-Content build/report.json
```

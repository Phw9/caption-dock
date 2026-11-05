# Caption Dock

Windows 11에서 화면의 영어 자막을 읽어 한국어로 번역하고, 화면 위에 표시합니다.
Teams의 영어 실시간 자막을 켠 뒤 번역할 영역을 드래그하면 됩니다. 번역과 OCR은
CPU에서 실행되며 모델은 실행파일에 포함되어 있습니다.

1. [릴리스](https://github.com/Phw9/caption-dock/releases/latest)에서
   `caption-dock-v0.1.6-portable.exe`를 내려받아 실행합니다.
2. Teams나 YouTube에서 영어 자막을 켭니다. 앱의 **영역 선택**을 누르고 영어
   자막 줄을 드래그합니다. **Esc**로 선택을 취소할 수 있습니다.
3. 선택한 영역에 보이는 대사들을 차례로 번역해 별도의 **번역창**에 표시합니다.
   제목 표시줄을 드래그해 이동하고, 창 가장자리로 크기를 조절하세요.
   **글씨 −/+** 또는 **Ctrl+마우스 휠**로 글씨 크기를 바꿀 수 있습니다.
   창을 이동하거나 크기를 바꿔도 새 번역이 도착할 때 위치가 유지됩니다.
4. **항상 위**를 끄면 Teams 화면을 앞에 둘 수 있습니다. 위로 스크롤하면 이전
   번역을 읽을 수 있고, **지우기**로 목록을 비웁니다. 창을 닫았다면 앱의
   **번역창** 버튼으로 다시 엽니다.
5. **일시정지**는 번역 목록을 남겨 둔 채 처리를 멈춥니다. 다시 시작하면 현재
   자막부터 새 목록으로 번역합니다. 원문 자막 위치가 바뀌면 영역을 다시 선택합니다.

Teams에서는 화자 이름과 발화 줄을 함께 선택하세요. 이름과 발화는 항상 분리해서
처리하며, 계정 열 왼쪽의 프로필 아이콘은 읽기에서 제외합니다.
이름은 작은 칩에 표시하고, 발화만 큰 글씨로 번역합니다. 이메일은 아이디
부분만 표시합니다. 화자가 바뀌면 문장을 서로 섞지 않습니다.
같은 화자의 ID가 반복되는 Teams 자막과, 위쪽이 잘리며 넘어가는 자막도
이미 처리한 문장을 반복 번역하지 않도록 연결합니다. 화면 속 대사 순서를
유지하고, 최근 100개 문장을 번역창에 남깁니다. 진행 중인 문장의 번역이
바뀌면 같은 항목을 갱신합니다.

앱은 이어지는 자막의 겹치는 단어를 합쳐 문장이 끝날 때 번역합니다.
문장부호 없이 자막 갱신이 약 1.8초 동안 멈추면 모은 부분까지 먼저 보여줍니다.
이후 문장이 이어지면 전체 문장으로 번역을 갱신합니다. 한 문장이 계속 길어질
때는 8초 또는 48단어에서 나누어 처리합니다.

앱은 선택한 영역의 픽셀, OCR 결과, 번역문을 메모리에서 처리합니다. 자막을
파일로 저장하거나 외부로 전송하지 않습니다. 실행 시 내장 런타임과 모델을 Windows
임시 폴더에 풀고 정상 종료 시 정리합니다. 번역창에는 캡처 제외를 적용합니다.
보안 정책으로 캡처가 차단된 화면은 읽을 수 없습니다.

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
Start-Process -Wait -FilePath ./dist/caption-dock-v0.1.6-portable.exe -ArgumentList '--self-test build/report.json'
Get-Content build/report.json
```

For timing diagnostics, pass `--performance-report build/timing.json`. This optional
report contains durations and word counts, never caption text or account names.

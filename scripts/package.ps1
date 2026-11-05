# Run from a dedicated release environment containing requirements-build.txt.
param(
    [string]$Python = (Join-Path $PSScriptRoot "../.venv/Scripts/python.exe"),
    [string]$NativeRoot = (Join-Path $PSScriptRoot "../build/native"),
    [string]$NativeInstall = (Join-Path $NativeRoot "install")
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$root = Split-Path -Parent $PSScriptRoot
$version = "0.1.3"
$exeName = "caption-dock-v$version-portable"
$Python = (Resolve-Path -LiteralPath $Python).Path
$NativeRoot = (Resolve-Path -LiteralPath $NativeRoot).Path
$NativeInstall = (Resolve-Path -LiteralPath $NativeInstall).Path

function Install-Library([string]$Source, [string]$Destination) {
    if (!(Test-Path -LiteralPath $Destination) -or
        (Get-FileHash -LiteralPath $Destination).Hash -ne (Get-FileHash -LiteralPath $Source).Hash) {
        Copy-Item -LiteralPath $Source -Destination $Destination
    }
}

Push-Location $root
try {
    New-Item -ItemType Directory -Force assets, build, dist, licenses | Out-Null
    $site = & $Python -c "import sysconfig; print(sysconfig.get_path('purelib'))"
    $ct2 = Join-Path $site "ctranslate2"
    Install-Library "$NativeInstall/bin/ctranslate2.dll" "$ct2/ctranslate2.dll"
    foreach ($dll in "cudnn64_9.dll", "libiomp5md.dll") {
        $library = Join-Path $ct2 $dll
        if (Test-Path -LiteralPath $library) {
            Remove-Item -LiteralPath $library
        }
    }
    Install-Library "$NativeInstall/bin/tesseract55.dll" "assets/tesseract.dll"
    Copy-Item LICENSE, THIRD_PARTY_NOTICES.md -Destination licenses
    $notices = @{
        "CTranslate2.txt" = "ct2/LICENSE"
        "cpu_features.txt" = "ct2/third_party/cpu_features/LICENSE"
        "ruy.txt" = "ct2/third_party/ruy/LICENSE"
        "cpuinfo.txt" = "ct2/third_party/ruy/third_party/cpuinfo/LICENSE"
        "clog.txt" = "ct2/third_party/ruy/third_party/cpuinfo/deps/clog/LICENSE"
        "spdlog.txt" = "ct2/third_party/spdlog/LICENSE"
        "fmt.txt" = "ct2/third_party/spdlog/include/spdlog/fmt/bundled/fmt.license.rst"
        "Tesseract.txt" = "tesseract/LICENSE"
        "Leptonica.txt" = "leptonica/leptonica-license.txt"
    }
    foreach ($name in $notices.Keys) {
        Copy-Item -LiteralPath (Join-Path $NativeRoot $notices[$name]) -Destination "licenses/$name"
    }
    Get-Content -LiteralPath "$NativeRoot/ct2/include/half_float/half.hpp" -TotalCount 18 |
        Set-Content -Encoding utf8 "licenses/half-float.txt"
    $basePython = & $Python -c "import sys; print(sys.base_prefix)"
    Copy-Item -LiteralPath "$basePython/LICENSE.txt" -Destination "licenses/Python.txt"
    $remote = @{
        "CC-BY-4.0.txt" = "https://creativecommons.org/licenses/by/4.0/legalcode.txt"
        "tessdata-fast.txt" = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE"
        "SentencePiece.txt" = "https://raw.githubusercontent.com/google/sentencepiece/v0.2.1/LICENSE"
        "SentencePiece-absl.txt" = "https://raw.githubusercontent.com/google/sentencepiece/v0.2.1/third_party/absl/LICENSE"
        "SentencePiece-darts-clone.txt" = "https://raw.githubusercontent.com/google/sentencepiece/v0.2.1/third_party/darts_clone/LICENSE"
        "SentencePiece-esaxx.txt" = "https://raw.githubusercontent.com/google/sentencepiece/v0.2.1/third_party/esaxx/LICENSE"
        "SentencePiece-protobuf-lite.txt" = "https://raw.githubusercontent.com/google/sentencepiece/v0.2.1/third_party/protobuf-lite/LICENSE"
        "nlohmann-json.txt" = "https://raw.githubusercontent.com/nlohmann/json/v3.11.2/LICENSE.MIT"
        "pybind11.txt" = "https://raw.githubusercontent.com/pybind/pybind11/v2.11.1/LICENSE"
        "BS-thread-pool.txt" = "https://raw.githubusercontent.com/bshoshany/thread-pool/v3.5.0/LICENSE.txt"
        "Tcl.txt" = "https://raw.githubusercontent.com/tcltk/tcl/core-8-6-15/license.terms"
        "Tk.txt" = "https://raw.githubusercontent.com/tcltk/tk/core-8-6-15/license.terms"
    }
    foreach ($name in $remote.Keys) {
        Invoke-WebRequest -Uri $remote[$name] -OutFile "licenses/$name"
    }
    $distributions = foreach ($name in "numpy", "pyyaml", "setuptools", "packaging", "pyinstaller") {
        Get-ChildItem -LiteralPath $site -Directory -Filter "$name-*.dist-info" |
            Select-Object -First 1
    }
    $distributions += Get-ChildItem -LiteralPath "$site/setuptools/_vendor" -Directory -Filter "*.dist-info"
    foreach ($dist in $distributions) {
        $licenseRoot = Join-Path $dist.FullName "licenses"
        if (!(Test-Path -LiteralPath $licenseRoot)) { $licenseRoot = $dist.FullName }
        Get-ChildItem -LiteralPath $licenseRoot -Recurse -File |
            Where-Object { $_.Name -match "LICENSE|COPYING|NOTICE" } |
            ForEach-Object {
                $relative = [IO.Path]::GetRelativePath($licenseRoot, $_.FullName)
                $target = Join-Path "$root/licenses/$($dist.BaseName)" $relative
                New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $target
            }
    }

    $vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
    $visualStudio = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    $redistributables = Get-ChildItem -Path "$visualStudio/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT" -Directory |
        Sort-Object FullName -Descending | Select-Object -First 1
    if (!$redistributables) { throw "The Visual C++ x64 redistributables are required." }

    & $Python -m PyInstaller --noconfirm --onefile --windowed --noupx --name $exeName `
        --distpath dist --workpath build/freeze --specpath build `
        --exclude-module PIL --exclude-module tesserocr `
        --collect-binaries ctranslate2 --add-binary "$($redistributables.FullName)/*.dll:." `
        --add-binary "$root/assets/tesseract.dll:assets" `
        --add-data "$root/assets/tessdata:assets/tessdata" `
        --add-data "$root/assets/opus:assets/opus" `
        --add-data "$root/licenses:licenses" "$root/caption_dock.py"

    Compress-Archive -Path licenses/* -DestinationPath "dist/caption-dock-v$version-licenses.zip" -Force
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath "dist/$exeName.exe").Hash.ToLowerInvariant()
    "$hash  $exeName.exe" | Set-Content -Encoding ascii "dist/$exeName.exe.sha256"
} finally {
    Pop-Location
}

# Requires Visual Studio 2026 C++ Desktop tools, CMake 4.2+, and PowerShell 7.
param([string]$BuildRoot = (Join-Path $PSScriptRoot "../build/native"))
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$build = [IO.Path]::GetFullPath($BuildRoot)
$prefix = Join-Path $build "install"
$generator = "Visual Studio 18 2026"
$leptonica = Join-Path $build "leptonica"
$tesseract = Join-Path $build "tesseract"
$ct2 = Join-Path $build "ct2"
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force $build | Out-Null

if (!(Test-Path $leptonica)) {
    git clone --depth 1 --branch 1.87.0 https://github.com/DanBloomberg/leptonica.git $leptonica
}
if (!(Test-Path $tesseract)) {
    git clone --depth 1 --branch 5.5.1 https://github.com/tesseract-ocr/tesseract.git $tesseract
}
if (!(Test-Path $ct2)) {
    git clone --depth 1 --branch v4.6.0 https://github.com/OpenNMT/CTranslate2.git $ct2
}
git -C $ct2 submodule update --init --recursive --depth 1 -- third_party/cpu_features third_party/ruy third_party/spdlog

cmake -S $leptonica -B "$build/lept-build" -G $generator -A x64 `
    "-DCMAKE_INSTALL_PREFIX=$prefix" -DBUILD_SHARED_LIBS=OFF -DBUILD_PROG=OFF `
    -DSW_BUILD=OFF -DENABLE_ZLIB=OFF -DENABLE_PNG=OFF -DENABLE_JPEG=OFF `
    -DENABLE_TIFF=OFF -DENABLE_GIF=OFF -DENABLE_WEBP=OFF -DENABLE_OPENJPEG=OFF
cmake --build "$build/lept-build" --config Release --target install --parallel 8

cmake -S $tesseract -B "$build/tess-build" -G $generator -A x64 `
    "-DCMAKE_PREFIX_PATH=$prefix" "-DCMAKE_INSTALL_PREFIX=$prefix" `
    -DBUILD_SHARED_LIBS=ON -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF `
    -DDISABLE_ARCHIVE=ON -DDISABLE_CURL=ON -DDISABLE_TIFF=ON `
    -DGRAPHICS_DISABLED=ON -DOPENMP_BUILD=OFF -DENABLE_LTO=OFF -DSW_BUILD=OFF
cmake --build "$build/tess-build" --config Release --target install --parallel 8

cmake -S $ct2 -B "$build/ct2-build" -G $generator -A x64 `
    "-DCMAKE_INSTALL_PREFIX=$prefix" "-DCMAKE_POLICY_VERSION_MINIMUM=3.5" `
    -DWITH_MKL=OFF -DWITH_DNNL=OFF -DWITH_CUDA=OFF -DWITH_RUY=ON `
    -DOPENMP_RUNTIME=NONE -DBUILD_CLI=OFF -DBUILD_TESTS=OFF
cmake --build "$build/ct2-build" --config Release --target install --parallel 8

New-Item -ItemType Directory -Force "$root/assets" | Out-Null
Copy-Item -LiteralPath "$prefix/bin/tesseract55.dll" -Destination "$root/assets/tesseract.dll"

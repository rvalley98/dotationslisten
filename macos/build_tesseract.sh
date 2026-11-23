#!/bin/bash
# Builds a self-contained tesseract binary (libpng, leptonica and libtesseract linked
# statically; only macOS system libraries are used dynamically) for macOS >= $MACOS_MIN.
# Homebrew's binaries only run on the macOS they were built for, so they cannot be shipped.
#
#   macos/build_tesseract.sh      -> macos/build/tesseract/{bin/tesseract,tessdata/}
set -euo pipefail

MACOS_MIN="${MACOS_MIN:-13.0}"
LIBPNG_VERSION=1.6.50
LEPTONICA_VERSION=1.87.0
TESSERACT_VERSION=5.5.1

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/build/src"
PREFIX="$HERE/build/deps"
OUT="$HERE/build/tesseract"
mkdir -p "$WORK" "$PREFIX" "$OUT/bin" "$OUT/tessdata"

export MACOSX_DEPLOYMENT_TARGET="$MACOS_MIN"
CMAKE_COMMON=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOS_MIN" -DCMAKE_OSX_ARCHITECTURES=arm64
              -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_PREFIX_PATH="$PREFIX" -DBUILD_SHARED_LIBS=OFF
              -DCMAKE_POLICY_VERSION_MINIMUM=3.5)

fetch() {  # url file
    [ -f "$WORK/$2" ] || curl -fsSL "$1" -o "$WORK/$2"
}

fetch "https://download.sourceforge.net/libpng/libpng-$LIBPNG_VERSION.tar.gz" libpng.tar.gz
fetch "https://github.com/DanBloomberg/leptonica/releases/download/$LEPTONICA_VERSION/leptonica-$LEPTONICA_VERSION.tar.gz" leptonica.tar.gz
fetch "https://github.com/tesseract-ocr/tesseract/archive/refs/tags/$TESSERACT_VERSION.tar.gz" tesseract.tar.gz

build() {  # name, extra cmake args...
    local name="$1"; shift
    rm -rf "$WORK/$name" && mkdir -p "$WORK/$name"
    tar -xzf "$WORK/$name.tar.gz" -C "$WORK/$name" --strip-components=1
    cmake -S "$WORK/$name" -B "$WORK/$name/build" "${CMAKE_COMMON[@]}" "$@" > "$WORK/$name.cmake.log"
    cmake --build "$WORK/$name/build" -j "$(sysctl -n hw.ncpu)" > "$WORK/$name.build.log"
    cmake --install "$WORK/$name/build" > /dev/null
}

echo "libpng ..."
build libpng -DPNG_SHARED=OFF -DPNG_TESTS=OFF -DPNG_TOOLS=OFF -DPNG_FRAMEWORK=OFF
echo "leptonica ..."
# only PNG is needed (pages are handed over as PNG); zlib comes from macOS
build leptonica -DSW_BUILD=OFF -DENABLE_PNG=ON -DENABLE_ZLIB=ON -DENABLE_GIF=OFF -DENABLE_JPEG=OFF \
    -DENABLE_TIFF=OFF -DENABLE_WEBP=OFF -DENABLE_OPENJPEG=OFF -DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=ON \
    -DPNG_LIBRARY="$PREFIX/lib/libpng.a" -DPNG_PNG_INCLUDE_DIR="$PREFIX/include"
echo "tesseract ..."
build tesseract -DSW_BUILD=OFF -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF -DDISABLE_ARCHIVE=ON -DDISABLE_CURL=ON \
    -DGRAPHICS_DISABLED=ON -DOPENMP_BUILD=OFF -DENABLE_LTO=OFF -DLeptonica_DIR="$PREFIX/lib/cmake/leptonica"

cp "$PREFIX/bin/tesseract" "$OUT/bin/tesseract"
strip -x "$OUT/bin/tesseract"

# configs (e.g. "tsv" output) as in the distribution packages
rm -rf "$OUT/tessdata/configs" "$OUT/tessdata/tessconfigs"
cp -R "$WORK/tesseract/tessdata/configs" "$WORK/tesseract/tessdata/tessconfigs" "$OUT/tessdata/"

# language data: German (titles, labels) and orientation detection - same files as Debian's packages
for lang in deu osd; do
    [ -f "$OUT/tessdata/$lang.traineddata" ] || \
        curl -fsSL "https://github.com/tesseract-ocr/tessdata/raw/main/$lang.traineddata" -o "$OUT/tessdata/$lang.traineddata"
done

echo "Abhängigkeiten:"; otool -L "$OUT/bin/tesseract" | tail -n +2
echo "macOS min: $(otool -l "$OUT/bin/tesseract" | grep -A4 LC_BUILD_VERSION | awk '/minos/ {print $2}')"
"$OUT/bin/tesseract" --version | head -1

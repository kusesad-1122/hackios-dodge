#!/bin/bash
# Build the open-source libraries XNU links into the non-Apple kernel.
# Keep their source revisions aligned with dada's xnu-deps/setup.sh.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TREE=${XNU_SRC:-$PWD}
ARCH=${XNU_ARCH:-arm64e}
WORK="$TREE/BUILD/deps"
NATIVE_SDK=$(xcrun --sdk iphoneos --show-sdk-path)
SDK_VERSION=$(xcrun --sdk iphoneos --show-sdk-version)
SDK=${XNU_SDK_PATH:-$WORK/iPhoneOS.xnu.sdk}
CLANG=$(xcrun -f clang)
LIBTOOL=$(xcrun -f libtool)
[ -f "$TREE/makedefs/MakeInc.def" ] || { echo "no XNU tree at $TREE"; exit 1; }

fetch() {
    local name=$1 tag=$2 revision=$3
    if [ ! -d "$WORK/$name/.git" ]; then
        git clone --depth 1 --branch "$tag" \
            "https://github.com/apple-oss-distributions/$name.git" "$WORK/$name"
    fi
    [ "$(git -C "$WORK/$name" rev-parse HEAD)" = "$revision" ] || {
        echo "$name does not match the pinned dada dependency revision"; exit 1;
    }
}
mkdir -p "$WORK"
fetch libdispatch libdispatch-1415.100.11 a641558f447659d90ad002ef0ee6f0212273fbfc
fetch libpthread libpthread-514.100.2 a6c70ca0e544347a0377babf748f831577ec24f9

# Add private open-source headers and archives without modifying Xcode's SDK.
mkdir -p "$SDK/usr"
for entry in "$NATIVE_SDK"/*; do
    [ "$(basename "$entry")" = usr ] || ln -sfn "$entry" "$SDK/"
done
for entry in "$NATIVE_SDK"/usr/*; do
    [ "$(basename "$entry")" = local ] || ln -sfn "$entry" "$SDK/usr/"
done
LOCAL="$SDK/usr/local"
mkdir -p "$LOCAL/include/kernel/os" "$LOCAL/lib/kernel" "$LOCAL/libexec"
cp "$NATIVE_SDK/usr/local/libexec/availability.pl" "$LOCAL/libexec/availability.pl"
chmod +x "$LOCAL/libexec/availability.pl"
if unifdef -DOS_FIREHOSE_SPI=1 -DKERNEL=1 \
    "$WORK/libdispatch/os/firehose_buffer_private.h" \
    > "$LOCAL/include/kernel/os/firehose_buffer_private.h"; then
    :
else
    status=$?
    [ "$status" -eq 1 ] || exit "$status"
fi
cp "$WORK/libdispatch/src/firehose/firehose_types.defs" "$LOCAL/include/kernel/os/"

export XNU_SRC="$TREE" XNU_ARCH="$ARCH" XNU_SDK_PATH="$SDK"
bash "$SCRIPT_DIR/xnu-build-darwin.sh" -j"$(sysctl -n hw.ncpu)" exporthdrs \
    2>&1 | tee "$WORK/exporthdrs.log"
HEADERS="$TREE/BUILD/obj/EXPORT_HDRS"
[ -d "$HEADERS/osfmk" ] || { echo "XNU headers were not exported"; exit 1; }

# These archives become part of XNU itself, so use its private interfaces and ABI.
COMMON=(-target "$ARCH-apple-ios$SDK_VERSION" -isysroot "$SDK" -c -Os -mkernel
    -nostdinc -fno-builtin -DKERNEL=1 -DKERNEL_PRIVATE=1 -DXNU_KERNEL_PRIVATE=1
    -DPRIVATE=1 -D__DARWIN_64_BIT_INO_T=1 -DARM64_BOARD_CONFIG_BCM2837)
for area in osfmk bsd libkern pexpert iokit security; do
    COMMON+=("-I$HEADERS/$area")
done
COMMON+=("-I$TREE/EXTERNAL_HEADERS" "-idirafter" "$SDK/usr/include")

"$CLANG" "${COMMON[@]}" \
    -DDISPATCH_USE_DTRACE=0 -DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1 \
    -DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0 -DOS_FIREHOSE_SPI=1 \
    -I"$WORK/libdispatch" -I"$WORK/libdispatch/src" -I"$WORK/libdispatch/src/firehose" \
    -I"$TREE/libkern/firehose" -I"$HEADERS/libkern/os" -I"$LOCAL/include/kernel" \
    -o "$WORK/firehose_buffer.o" "$WORK/libdispatch/src/firehose/firehose_buffer.c"
"$LIBTOOL" -static -o "$LOCAL/lib/kernel/libfirehose_kernel.a" "$WORK/firehose_buffer.o"

# The two renames avoid collisions when the pthread kext is linked into XNU.
PTHREAD="$WORK/libpthread"
for file in kern_init kern_support kern_synch; do
    "$CLANG" "${COMMON[@]}" -fno-common -Wno-int-conversion \
        -D__PTHREAD_EXPOSE_INTERNALS__=1 -Dpthread_kern=pthread_kext_kern \
        -Dcurrent_uthread=pthread_kext_current_uthread \
        -I"$PTHREAD" -I"$PTHREAD/include" -I"$PTHREAD/private" \
        -o "$WORK/pthread_$file.o" "$PTHREAD/kern/$file.c"
done
"$LIBTOOL" -static -o "$LOCAL/lib/kernel/libpthread_kext.a" \
    "$WORK/pthread_kern_init.o" "$WORK/pthread_kern_support.o" "$WORK/pthread_kern_synch.o"
file "$WORK/firehose_buffer.o" "$WORK/pthread_kern_init.o"
echo "XNU dependencies ready in $SDK"

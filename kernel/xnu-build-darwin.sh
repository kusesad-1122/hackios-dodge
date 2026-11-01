#!/bin/bash
# Build xnu-12377.121.6 (iOS 26's kernel) as arm64e on macOS.
#
# This is dada's xnu-build.sh cut down to what a macOS runner needs: on Darwin
# the cctools, mig and the SDK come from Xcode, so there is no xnu-deps to set
# up, no hostcompat shims, and no libfirehose/pthread prebuilt libraries. What
# remains is the make invocation and the flags the arm64e build needs.
#
# Run from the patched tree's root:
#   XNU_ARCH=arm64e MACHINE=BCM2837 RC_DARWIN_KERNEL_VERSION=12377.121.6 \
#     bash kernel/xnu-build-darwin.sh
set -u

TREE=${XNU_SRC:-$PWD}
cd "$TREE" || { echo "no tree at $TREE"; exit 1; }
[ -f makedefs/MakeInc.def ] || { echo "$TREE is not an XNU tree"; exit 1; }

ARCH=${XNU_ARCH:-arm64e}
MACH=${MACHINE:-BCM2837}
VER=${RC_DARWIN_KERNEL_VERSION:-12377.121.6}

# ARCH_CONFIGS selects XNU's architecture configuration (ARM64), not the ABI:
# MakeInc.def line 382 reads
#     ARCH_FLAGS_ARM64 = -arch $(ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG)
# so arm64e goes in through ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG. Passing
# ARCH_CONFIGS=arm64e picks a configuration that does not exist and the build
# falls back to the host's own (that is what
# "build_setup_bootstrap_DEVELOPMENT^X86_64^NONE" in an earlier run meant).

# The objects of an arm64 and an arm64e build land in the same directory (the
# machine configuration names it, not the architecture), so make cannot tell
# them apart. Start over when the architecture changes.
STAMP=BUILD/obj/.arch
if [ -d BUILD/obj ] && [ "$(cat "$STAMP" 2>/dev/null)" != "$ARCH" ]; then
	echo "xnu-build: architecture changed to $ARCH: discarding BUILD/obj"
	rm -rf BUILD/obj
fi
mkdir -p BUILD/obj && echo "$ARCH" > "$STAMP"

# The XNU makefiles do not survive a path with spaces.
case "$PWD" in
	*' '*) echo "xnu-build: the tree path contains a space: $PWD"; exit 1;;
esac

# On Darwin the toolchain is Xcode's. Say where, explicitly, rather than relying
# on the runner's defaults.
SDK=$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null)
[ -d "$SDK" ] || { echo "xnu-build: no iphoneos SDK from xcrun"; exit 1; }

echo "xnu-build: tree      $PWD"
echo "xnu-build: arch      $ARCH"
echo "xnu-build: machine   $MACH"
echo "xnu-build: version   $VER"
echo "xnu-build: SDK       $SDK"
echo "xnu-build: clang     $(xcrun -f clang)  $(clang --version | head -1)"
echo

# -k is required: what is left after the link are the export check and three
# symbolsets, and the kernel file is written before them. Both dada's notes and
# base/xnu/README.md say the same: judge by the file, not by make's exit status.
exec make \
	SDKROOT="$SDK" \
	BUILD_WERROR=0 \
	BUILD_LTO=0 \
	DO_CTFMERGE=0 \
	BUILD_DSYM=0 \
	ARCH_CONFIGS=ARM64 \
	MACHINE_CONFIGS="$MACH" \
	KERNEL_CONFIGS=DEVELOPMENT \
	ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG="$ARCH" \
	RC_DARWIN_KERNEL_VERSION="$VER" \
	"$@" \
	-k

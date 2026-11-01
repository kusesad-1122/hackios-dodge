# dodge — OnePlus 13 (PJZ110, SM8750) running iOS 26

Port of [HakiOS](https://github.com/superboyyy/hakios-arm64e-dada) (iOS 26 / arm64e on the
Snapdragon 8 Elite) to the OnePlus 13, codename **dodge**.

Base: `superboyyy/hakios-arm64e-dada` at `f1ae906` — iOS 26 (`xnu-12377.121.6`, arm64e)
running on the Xiaomi 15, which is the same SoC (SM8750 / "sun" / Pakala).

> Nothing here has been flashed to a phone yet. Every address was read out of this phone's
> own device tree, and every claim below names the check that proves it.

## What this adds over dada

dada and dodge are the same SoC but different phones, and two things in dada's code assumed
there would only ever be one of them:

**1. The loader told them apart by framebuffer address.** Both report `0xFC800000`, and
`platform_dada` is listed first, so a OnePlus 13 booted as a Xiaomi 15. `struct platform`
grew `panel_width`/`panel_height`, and the match now compares the panel size:

| phone | fb_base | panel |
|---|---|---|
| Xiaomi 15 (dada) | `0xFC800000` | 1200×2670 |
| OnePlus 13 (dodge) | `0xFC800000` | **1440×3168** |
| POCO X5 Pro (redwood) | `0xE1000000` | 1080×2400 |

**2. The kernel could not ask which phone it was on.** dada carries 100 `dada*` boot-args
(`dadaadsp`, `dadagpu`, `dadacpu`, …) and a file-local `static bool dada;` in each driver.
That does not extend to a second phone. `bsd/dev/hakios_soc.c` is now the one place that
knows: the loader already writes the platform name into `/arm-io`'s `device_type`
(`base/xnuloader/loader.c:4151`), so the kernel reads its own identity from the tree it was
handed, in a `__startup_func` (the read only works before `PE_init_iokit()`, the same
constraint `bsd/dev/arm64/sysctl.c` works under).

`redwood_adsp.c` is the first driver converted: its addresses come from the SoC layer
instead of being copied in. The two phones agree on every address **except the ADSP
window's size** — `0x5080000` here, `0x4580000` on dada — and getting that wrong makes the
DSP's shared memory run past the end of its window.

## The phone's own numbers

Read from `fdt.bin`, the live device tree pulled from the running phone, decoded with `dtc`
(`backup/out/hw/hw/device-tree.dts`):

| | |
|---|---|
| model | `Qualcomm Technologies, Inc. Sun MTP,dodge` |
| compatible | `qcom,sun-mtp qcom,sun qcom,sunp-mtp qcom,sunp qcom,mtp` |
| GIC | `0x16000000`, redistributor `0x16080000`, stride `0x40000` |
| cores | 8, MPIDR `0x0..0x500` then `0x10000`, `0x10100` |
| UFS | `ufshc@1d84000` |
| GPU | `Adreno830v2` |
| panel | `1440×3168` (120/90/60 Hz), `mdss_dsi_panel_AA569_P_3_A0019_dsc_cmd` |
| touch | Synaptics `S3910` |
| SMEM / cmd_db | `0x81d00000` / `0x81c60000` |
| ADSP | `0x9ee00000` + `0x5080000` |

## Building the kernel

**On macOS (what the CI does).** `base/xnu/README.md`: on a Mac the cctools, `mig` and the
SDK come from Xcode and theos is not needed. `.github/workflows/build-kernel.yml` runs
`macos-14` and uploads `mach.development.bcm2837`.

```
XNU_ARCH=arm64e MACHINE=BCM2837 RC_DARWIN_KERNEL_VERSION=12377.121.6 ./xnu-build.sh -j -k
```

`-k` is required and its errors are harmless — they all come after the kernel is linked.

**Why not Linux.** A Linux clang knows the names `__builtin_ptrauth_sign_unauthenticated`
and friends but has no implementation: every combination of `arm64e`, `-march=armv8.3-a+pauth`
and `-Xclang -target-feature -Xclang +ptrauth` still fails with *"this target does not support
pointer authentication"*. Those builtins are what `HAS_APPLE_PAC` compiles to, and this board
uses `HAS_STD_PAC` anyway (`pexpert/pexpert/arm64/BCM2837.h` says so in its own comment).

## Checking it

```
python check-dodge.py         # profile vs loader vs the phone's device tree — 27 checks
python check-soc.py           # the SoC layer vs the phone's device tree — 23 checks
python check-kernel-dodge.py  # the layer is in the tree, in conf/files, and used
```

Each one reads the real `device-tree.dts` and the real C, and each fails when a value is
wrong (verified by injecting one: changing the GIC stride to `0x20000` fails three checks).

## Layout

```
kernel/xnu-12377.121.6-dodge.patch   the SoC layer + the ADSP change, on top of dada's patch
loader/                             the loader's platform row and match rule
soc/                                hakios_soc.{c,h}
.github/workflows/build-kernel.yml  the macOS kernel build
check-*.py                          the checkers
```

## Licence

dada's tree is built on Apple's open-source XNU; the patches here carry the same terms.

<!-- build trigger: 2026-11-01T15:53:30.6671293+08:00 -->

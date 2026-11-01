# The kernel build

`.github/workflows/build-kernel.yml` is kept out of the default branch for one
mechanical reason: pushing a workflow file needs a token with the `workflow`
scope, and the one in use here has `gist`, `read:org`, `repo`.

Add the scope and push it:

```sh
gh auth refresh -h github.com -s workflow
git add .github/workflows/build-kernel.yml
git commit -m "ci: build the kernel on macOS"
git push
```

## Why macOS and not Linux

Apple's XNU build wants three things a Linux host does not have:

| what | why Linux cannot do it |
|---|---|
| `__builtin_ptrauth_sign_unauthenticated` and friends | Ubuntu clang 18/19/20 *know* the names (`__has_builtin` is true) but have **no implementation**: every target and `-march` combination fails with `this target does not support pointer authentication`. Measured, not assumed. |
| `iig` | Apple's Interface Builder generator for kernel MIG stubs is closed-source; the tree has a shim, but the iOS 26 dispatch (`Panic`, `SetPowerOverride`) needs the real one. |
| `libfirehose_kernel.a` | xnu-12377's `upsi.h` carries `#error upsi.h is XNU private`, which stops the stage-2 library build on Linux. |

`base/xnu/README.md` says the same in its own words: on macOS "the cctools,
`mig` and the iOS SDK come from Xcode", and theos is not needed.

So one Linux-only obstacle was worked around and is documented here: the board
header defines `HAS_APPLE_PAC 1` on arm64e, and the kernel's own comment says
this board uses `HAS_STD_PAC` instead. On a Linux clang the Apple-PAC paths
cannot compile at all, which is what the 11 pointer-authentication errors were.

## What the build produces

`BUILD/obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837` — the kernel the
loader boots. The workflow checks that it contains `_hakios_soc_device`,
`_hakios_soc_facts` and `_hakios_soc_is_sm8750`, and the strings `dodge`,
`dada` and `sm8750`, before uploading it.

`-k` is required and is not a workaround for our code: the remaining complaints
all come *after* the kernel is linked (the export check and three symbolsets).
Both dada's notes and `base/xnu/README.md` say the same.

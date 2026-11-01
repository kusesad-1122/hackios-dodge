#!/bin/bash
# Build the same Wi-Fi object as dada f1ae906; do not substitute linker stubs.
set -euo pipefail
TREE=${XNU_SRC:-$PWD}
ROOT="$TREE/BUILD/wifi"
BASE=f1ae906fcc43ba8f763663257724ba938fb820ab
mkdir -p "$ROOT/tools" "$ROOT/xnu-deps/host/bin"
curl --fail --location \
    "https://raw.githubusercontent.com/superboyyy/hakios-arm64e-dada/$BASE/base/tools/mk-ath12k.sh" \
    -o "$ROOT/tools/mk-ath12k.sh"

# This staged script is a regular file, so dirname is sufficient on both hosts.
python3 - "$ROOT/tools/mk-ath12k.sh" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
old = 'ROOT=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)'
new = 'ROOT=$(cd "$(dirname "$0")/.." && pwd)'
assert text.count(old) == 1, 'dada ath12k script root expression changed'
path.write_text(text.replace(old, new))
PY
ln -sfn "$(xcrun -f ld)" "$ROOT/xnu-deps/host/bin/ld64"
bash "$ROOT/tools/mk-ath12k.sh"
OBJECT="$ROOT/xnu-deps/build/ath12k/out/ath12k.o"
[ -s "$OBJECT" ] || { echo "ath12k did not produce its linked object"; exit 1; }
python3 - "$OBJECT" <<'PY'
import pathlib, struct, sys
path = pathlib.Path(sys.argv[1])
magic, cpu, subtype = struct.unpack('<III', path.read_bytes()[:12])
assert magic == 0xfeedfacf and cpu == 0x0100000c, 'not an ARM64 Mach-O'
assert subtype & 0x00ffffff == 2, 'ath12k object is not arm64e'
assert subtype & 0x80000000, 'ath12k object lacks the pointer-authentication ABI bit'
print('ath12k:', path.stat().st_size, 'bytes, cpusubtype=%#010x' % subtype)
PY
nm -g "$OBJECT" | grep ' _nw_wifi_'

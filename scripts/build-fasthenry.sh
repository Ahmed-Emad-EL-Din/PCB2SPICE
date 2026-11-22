#!/usr/bin/env bash
# Build MIT FastHenry 3.0.1 (64-bit) and install it where the worker finds it.
#
#   ./scripts/build-fasthenry.sh            # -> worker/vendor/fasthenry/fasthenry
#   FH_PREFIX=/opt/fasthenry ./scripts/build-fasthenry.sh
#
# Requires: git, make, a C compiler. Tested with GCC 14 on Debian trixie.
set -euo pipefail

FH_PREFIX="${FH_PREFIX:-$(cd "$(dirname "$0")/.." && pwd)/worker/vendor/fasthenry}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> cloning FastHenry2 (MIT / FastFieldSolvers 64-bit port)"
git clone --depth 1 https://github.com/ediloren/FastHenry2.git "$WORK/fh" >/dev/null 2>&1
cd "$WORK/fh"

# The source is 1996-era K&R C. GCC >= 14 rejects several constructs that
# were merely warnings for 25 years. gnu89 + -fcommon + these -Wno- flags
# reproduce the behaviour the code was written for.
COMMON='-O2 -std=gnu89 -fcommon -Wno-implicit-function-declaration -Wno-implicit-int -Wno-incompatible-pointer-types -Wno-int-conversion -Wno-return-mismatch -Wno-builtin-declaration-mismatch'

# `config` is not executable in the upstream repo — invoke it through sh.
# If it fails for any reason, fall back to copying the x64 Makefiles directly.
if ! sh ./config x64 >/dev/null 2>&1; then
  cp src/fasthenry/Makefile.x64 src/fasthenry/Makefile
  cp src/zbuf/Makefile.x64      src/zbuf/Makefile
fi
test -f src/fasthenry/Makefile        || cp src/fasthenry/Makefile.x64 src/fasthenry/Makefile
test -f src/fasthenry/sparse/Makefile || echo "FATAL: sparse/Makefile missing" >&2

# Replace every existing CFLAGS assignment (the FIRST match only — sparse/Makefile
# has a commented-out one further down) with our modern-compiler flags.
sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -DFOUR -m64|"  src/fasthenry/Makefile
sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -m64|"         src/fasthenry/sparse/Makefile
sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -DOTHER -m64|" src/zbuf/Makefile
grep -q "gnu89" src/fasthenry/Makefile || { echo "FATAL: CFLAGS patch did not apply" >&2; exit 1; }

echo "==> building"
# `make all` also tries to build the misc/ utilities, which fail to compile on
# modern GCC. We only need bin/fasthenry, so don't treat that as fatal.
make fasthenry 2>&1 | tail -5 || true

if [ ! -x bin/fasthenry ]; then
  echo "BUILD FAILED — bin/fasthenry not produced" >&2
  exit 1
fi

mkdir -p "$FH_PREFIX/bin"
install -m 0755 bin/fasthenry "$FH_PREFIX/bin/fasthenry"
echo "==> installed $FH_PREFIX/bin/fasthenry"

# smoke test: DC resistance of 10 mm x 0.3 mm x 35 µm copper must be 16.381 mΩ
T="$(mktemp -d)"
cat > "$T/dc.inp" <<'INP'
.units mm
.default sigma = 58139.5
n1 x=0 y=0 z=0
n2 x=10 y=0 z=0
e1 n1 n2 w=0.3 h=0.035 nhinc=1 nwinc=1
.external n1 n2
.freq fmin=0 fmax=0 ndec=1
.end
INP
( cd "$T" && "$FH_PREFIX/bin/fasthenry" dc.inp >/dev/null 2>&1 )
R="$(sed -n '3p' "$T/Zc.mat" | awk '{print $1}')"
rm -rf "$T"
# FastHenry reports OHMS. 10 mm x 0.3 mm x 35 um copper @ 1.72e-8 Ω·m
#   R = rho*L/A = 16.381 mΩ = 0.016381 Ω
echo "==> smoke test: R_dc = $R Ω (expected 0.016381 Ω)"
python3 - "$R" <<'PY'
import sys
r = float(sys.argv[1])
assert abs(r - 0.016381) / 0.016381 < 0.02, f"DC resistance off by more than 2%: {r} Ω"
print("==> smoke test PASSED")
PY

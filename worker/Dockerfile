# PCB Parasitic Engine — Tier A + Tier B worker (FastAPI + FastHenry2)
#
# Two-stage build:
#   1. builder  — compiles MIT FastHenry 3.0.1 (64-bit port) from source
#   2. runtime  — slim Python image with the solver binary baked in
#
# FastHenry is MIT-licensed (see NOTICE.md); we build it from the
# FastFieldSolvers-maintained 64-bit port rather than vendoring a binary.
FROM debian:trixie-slim AS fh-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates git make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/ediloren/FastHenry2.git .

# The 1996 C code needs a few modern-compiler accommodations:
#  -std=gnu89 keeps K&R semantics, -fcommon restores tentative definitions,
#  and the -Wno-* flags silence the K&R-vs-C99 errors GCC >= 14 raises.
# NOTE: `config` is not executable upstream -> invoke via sh, and verify the
# sed actually applied (a silent miss produces a fresh-clone build failure).
RUN set -eu; \
    COMMON='-O2 -std=gnu89 -fcommon -Wno-implicit-function-declaration -Wno-implicit-int -Wno-incompatible-pointer-types -Wno-int-conversion -Wno-return-mismatch -Wno-builtin-declaration-mismatch'; \
    sh ./config x64 >/dev/null 2>&1 || { cp src/fasthenry/Makefile.x64 src/fasthenry/Makefile; cp src/zbuf/Makefile.x64 src/zbuf/Makefile; }; \
    sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -DFOUR -m64|"  src/fasthenry/Makefile; \
    sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -m64|"         src/fasthenry/sparse/Makefile; \
    sed -i "0,/^CFLAGS = .*/s||CFLAGS = $COMMON -DOTHER -m64|" src/zbuf/Makefile; \
    grep -q gnu89 src/fasthenry/Makefile; \
    make fasthenry; \
    chmod +x bin/fasthenry; \
    ldd bin/fasthenry


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data/sessions \
    TTL_SECONDS=3600 \
    FH_BIN=/opt/fasthenry/bin/fasthenry

WORKDIR /app
COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Tier B solver
COPY --from=fh-builder /src/bin/fasthenry /opt/fasthenry/bin/fasthenry
RUN chmod +x /opt/fasthenry/bin/fasthenry \
 && /opt/fasthenry/bin/fasthenry 2>&1 | head -2 || true

COPY worker/pcb_engine ./pcb_engine
COPY worker/main.py ./main.py
COPY worker/fixtures ./fixtures

# non-root, data dir owned by app user
RUN useradd --create-home --uid 10001 engine && mkdir -p /data/sessions && chown -R engine:engine /data /app
USER engine

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)); assert d['status']=='ok'"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

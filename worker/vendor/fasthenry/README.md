# FastHenry2 binary (built, not committed)

`fasthenry` here is produced by `scripts/build-fasthenry.sh` (or by the builder
stage of `worker/Dockerfile`). It is **git-ignored** — binaries are
platform-specific and this repo does not redistribute them.

Source: https://github.com/ediloren/FastHenry2 (MIT / FastFieldSolvers 64-bit port
of MIT FastHenry 3.0.1, 2012-05-28). License text: `NOTICE.md` at the repo root.

Rebuild:

```bash
./scripts/build-fasthenry.sh          # -> worker/vendor/fasthenry/bin/fasthenry
```

Verify what the worker sees:

```bash
curl -s localhost:8000/health | python3 -m json.tool | grep -A6 solvers
```

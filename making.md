# making.md — Handoff / Continuation Guide (read me first)

> **Project:** PCB Parasitic Engine for QSPICE (`pcb-parasitic-qspice`)
> **Purpose of this file:** anyone — you, me in a new chat, *any other AI* — must be able to pick up this project and continue without losing a single decision, fact, or pitfall. **Keep this file current:** whenever state changes (task done, decision locked, file moved), update it in the same commit.
> **Last updated:** 2026-11-22 (Sprint 2 — **Tier B PEEC field solver live**) · **Owner:** repo at `/home/user/pcb-parasitic-qspice` (git branch `main`) · Drive mirror: folder "PCB Parasitic Engine for QSPICE" (`1gCw61aLNj_gfCBfma3RrMhbTjHtA43b7`)

---

## 0. TL;DR for a brand-new chat

1. Work happens in the **git repo** `/home/user/pcb-parasitic-qspice`. In an Arena session the folder `/home/user` persists across messages of the *same* conversation — but **do not assume another chat sees these files**. If the new chat runs on a different machine/platform, obtain the repo via GitHub (once you push — see §7) or via the Drive ZIP `pcb-parasitic-qspice-*.zip` in the Drive folder above.
2. Read, in order: this file → `plan.md` (source of truth for tasks) → `README.md` → `docs/RESEARCH.md` → `docs/SKILLS.md`.
3. Find the first unchecked task in `plan.md`. As of 2026-11-22 the Tier A slice **and Tier B PEEC field solver (FastHenry2)** are **built and verified** (see §2). Highest-value next items: **T-304** (capacitance field solve — currently blocked, read the note in `plan.md` before touching it), **T-303b** (multi-port solve → mutual L → `K` statements), **T-306** (frequency sweep → Foster ladder), **T-204** (Gerber path), **T-202** (QSPICE ZIP inventory), **T-308** (parasitics.json schema), **T-406** (ngspice verification gate). For each task:
   - tick the checkbox with date,
   - update "Last updated",
   - `git add -A && git commit -m "T-xxx: …"` (one commit per task ID),
   - if you changed decisions, append to the Decision log **and mirror the updated files to Google Drive** (folder ID above; use Drive connector `upload_file` again).
4. Never skip the plan-tick step. The plan is the contract.
5. **Do not trust conversational memory — trust the files.** If files and memory disagree, believe the files.

---

## 1. What we are building (one paragraph)

A web app: user uploads a **QSPICE project (.zip)** and a **PCB design** (KiCad `.kicad_pcb` first; Gerber+drill second). The app extracts the parasitic **R (skin/proximity), self/mutual L, C** that physical copper introduces on every net, then produces a **new downloadable .zip** where those effects are injected into the project — `.cir` netlist rewrite (default, robust) **and/or** an additive "PCB Parasitics" block in `.qsch` (opt-in) — plus a professional **engineering report** (PDF/HTML) with per-net values, solver provenance, convergence data, passivity audit, uncertainty bounds, and a before/after diff. **v1.0 focus: power-electronics commutation loops** (half-bridge overshoot/ringing — the use case validated against measurement by TU Ilmenau and the PCBParC project).

---

## 2. Current state (2026-11-22, after Sprint 2 — Tier B live)

| Item | Status |
|---|---|
| Repository | `main` at `/home/user/pcb-parasitic-qspice`; Sprint 1 commit added (apps/web, worker/, CI, Docker, compose) |
| Research (papers, solvers, format byte-level verification of `.qsch`) | **Done** — `docs/RESEARCH.md` |
| README / plan.md / SKILLS.md / LICENSE (MIT, open-core) / NOTICE.md | **Done**, README rewritten for the live vertical slice (screenshots in `docs/assets/`) |
| Decisions OQ-01…OQ-06 | **Locked** — see §5 |
| **Tier A vertical slice** | **Implemented & verified live** — upload `.kicad_pcb` + QSPICE project ZIP → analysis → injection → report. See `plan.md` "Progress log — Sprint 1" |
| **Tier B PEEC field solver** | **LIVE & validated** — `worker/pcb_engine/field.py` builds FastHenry `.inp` from KiCad geometry (finite plane, inferred vias, real layer z), solves, parses `Zc.mat`, runs a mesh-convergence study. `scripts/build-fasthenry.sh` builds the MIT 64-bit solver + self-verifies. UI + report show A vs B side by side; injection uses B. **Read `docs/TIER-B.md` before touching it** — it documents the 5 traps that cost hours |
| Validation headline | DC R exact (0.00 %), MIT `plane.in` +0.9 %, straight-trace loop L vs microstrip +7.7 %; SW on a finite plane reads **+46.6 %** vs Tier A — that is physics, not a bug |
| Engine tests | **26/26 green** (`python3 -m unittest discover -s worker/tests -v`); 9 of them are Tier B |
| Web build | `next build` clean (static prerender, 87 kB shared JS); `tsc --noEmit` clean |
| CI | `.github/workflows/ci.yml` (engine tests + web typecheck/build) — no remote yet, CI validated locally |
| GitHub remote | **None yet** — no GitHub connector in Arena (`list_connector_tools github` → `unsupported`). Push per §7 when connected |
| Google Drive | Mirror needs refresh after this commit (making.md, README.md, plan.md + new ZIP) — **do it; don't assume the old mirror is current** |
| Running services (this session) | web dev server :3000 (`npm run dev`, WORKER_URL=http://127.0.0.1:8000) · FastAPI worker :8000 |

**Milestone:** M0 "Approved foundation" — T-010 done. Sprint 1 overshoots into M2/M4/M6 territory (thin slices of ingestion, injection, UI) without claiming those milestones complete.

**How to run (today):**
```bash
pip install -r worker/requirements.txt
./scripts/build-fasthenry.sh                       # OPTIONAL — enables Tier B (MIT solver, self-verified)
FH_BIN=$PWD/worker/vendor/fasthenry/fasthenry \
  python3 -m uvicorn main:app --app-dir worker --host 0.0.0.0 --port 8000 &   # engine
npm --prefix apps/web ci && WORKER_URL=http://127.0.0.1:8000 npm --prefix apps/web run dev
# → http://localhost:3000 (demo: upload worker/fixtures/probe_board.kicad_pcb + any project zip)
# Check what you actually have:  curl -s localhost:8000/health | jq .solvers
```

**Tier B invariants (do not regress — each one was a real bug):**
- `.units mm` in FastHenry **scales resistivity by the length unit** → σ must be `5.814e4`, not `58.14`. Wrong value = exactly 1000× too much R.
- `npfar`/`npnear` (plane reference nodes) must be `+` **continuation lines of the `g1` block**, never emitted after the element list.
- Vias are **inferred** (two copper layers meeting at the same x,y), never declared *and* inferred — duplicates produce coincident filaments and garbage R.
- Reference-plane gap searches must index by **stackup position**, not copper index.
- Use the **FastFieldSolvers 64-bit port**, not the 1996 MIT tarball (its `ualloc()` has no prototype → implicit `int` → truncated pointers → segfault).
- Tier B never silently degrades: no binary → `/health` false, UI banner, report header, `meta.json`; `tier=B` without a binary = HTTP 422.

**Key invariants (do not regress):**
- `.qsch` injection is **additive-only**; `.cir` injection is the **boundary-anchor model** (independent source V/I keeps original node; else first referencing device anchors; token-level anchoring). Whole-net naive re-pointing was tried and produced floating ladders — see decision log 2026-11-22.
- Node matching in `.cir` is **case-insensitive** (SPICE semantics).
- Files starting with `(` (KiCad s-expr) are **never** rewritten.
- Vendored/anonymous TTL sessions: `DATA_DIR` env (default `/tmp/pcb-parasitic-sessions`), 1 h TTL, `DELETE /api/session/{token}`.

---

## 3. Verified technical facts (byte-level, 2026-11-22)

Verified by downloading a real `.qsch` (public example `noise.qsch`) and hexdumping locally:

- `.qsch` = **magic `FF D8 FF DB`** (misdetected as JPEG by `file`, harmless).
- Text is **single-byte ASCII**, indented 2 spaces/level. High-byte markers:
  - `0xAB` prefixes every record payload line (`schematic`, `component`, `symbol`, `wire`, `junction`, `net`, `text`, `library file: …`).
  - `0xBB` terminates most record lines; a line containing only indent+`0xBB` closes a nested block.
- Net topology lives in records like `… «wire (x1,y1) (x2,y2) "NET"»`, `«net (x,y) … "GND"»`, `«junction (x,y)»`, coordinates are integer internal units (grid≈100; component pins at ±200; mm/mil mapping **TBD empirically** in T-402).
- Embedded SPICE directives: `library file: |.model 2N3904 NPN(...)` (note `|` prefix escaping).
- `.cir` export: QSPICE GUI → View → Netlist, or `QUX -Netlist "file.qsch"`; `.cir` is **not** auto-saved; `.net` not a QSPICE file (that's KiCad). `.qraw` = waveform output. QSPICE batch: `QSPICE64.exe file.cir` (community wraps binary as `qspice`). **QSPICE is Windows-only, freeware from Qorvo, do NOT bundle it.**
- File types: `.qsch .qsym .cir .qraw .pfg .v .cpp .lib`.
- uType: **.qsch additive-only edits by design** (never rewrite existing bytes); full rewire is post-MVP.
- Gerber/Excellon carry **no dielectric stackup** → KiCad-first strategy (`.kicad_pcb` embeds thickness/εr/copper per layer) or guided stackup wizard.
- ngspice = headless Linux verification proxy; final fidelity check must happen on the user's QSPICE (documented step in report appendix).
- Extraction theory: PEEC (Ruehli 1974); open-source MIT solvers FastHenry2 (R/L/M, planes) + FasterCap/FastCap2 (C); FastImp (wideband); openEMS (FDTD, GPL-3, subprocess only). Closed-form Tier A: IPC-2141A microstrip/stripline, Hammerstad–Jensen, Grover/Rosa partial inductance, Skin δ = √(2ρ/ωμ₀). See RESEARCH §2 for formulas + validity guard rails (encode them!).
- Validation benchmarks to replicate: TU Ilmenau (IEEE #9472438), PCBParC (ResearchGate #254042181), golden geometries in RESEARCH §7.
- Passivity of extracted matrices: audit always; Foster/vector-fitting (Gustavsen–Semlyen 1999) if curve-fitting frequency-dependent R.

Unknowns to measure during implementation: `.qsch` unit↔mm mapping (T-402); `.qsch` variants across QSPICE releases (scan ≥30 files, T-402); QSPICE `K` mutual-coupling edge cases (T-401); ngspice vs QSPICE numeric parity (T-406); KiCad `.net` vs `.qsch` net-name bridging strategy (T-207).

---

## 4. Target architecture (Vercel-locked)

```
┌────────────────────── Vercel ──────────────────────┐
│ apps/web  Next.js 15 (App Router, React 19, TS)     │
│  ├─ UI (upload, stackup wizard, mapping, results)   │
│  ├─ Route Handlers: zip inventory, validation,      │
│  │   Tier A closed-form (packages/kernel, TS)       │
│  ├─ Preview deployments on every PR (mock worker)   │
│  └─ Storage: Postgres (Neon/Supabase) + Upstash     │
└───────────┬─────────────────────────────────────────┘
            │ signed job dispatch (JWT) + SSE progress
┌───────────▼──── Fly.io / Railway / Cloud Run / VM ─┐
│ worker (Python 3.12 + FastAPI, Docker)              │
│  ├─ packages/engine: PEEC orchestration              │
│  ├─ FastHenry2 / FasterCap (subprocesses, sandbox)  │
│  ├─ ngspice verification harness                     │
│  └─ artifacts → S3 / Cloudflare R2                  │
└──────────────────────────────────────────────────────┘
Local dev: `docker compose up` runs BOTH.
Without worker: app runs in clearly-labeled "Tier A instant" mode.
```

**Hard constraint:** Vercel serverless cannot run native solver binaries or minutes-long jobs (size/timeout). Vercel = UI + Tier A only. Tier B/C = container worker only. (Risk R-11.)

**Monorepo layout (planned):**
```
pcb-parasitic-qspice/
├── apps/web/            # Next.js (Vercel)
├── packages/kernel/     # TS Tier A formulas (shared, unit-tested)
├── worker/              # Python FastAPI + solvers (Docker)
├── packages/engine/     # Python PEEC orchestration (inside worker)
├── docs/                # RESEARCH.md, SKILLS.md
├── fixtures/            # synthetic boards + PUBLIC .qsch specimens (careful licensing)
├── making.md, plan.md, README.md, NOTICE.md, LICENSE, .gitignore
└── vercel.json, docker-compose.yml, .github/workflows/ci.yml
```

**Env vars (planned):** `NEXT_PUBLIC_APP_URL`, `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT|REGION|BUCKET|KEY|SECRET`, `WORKER_URL` (+short-lived JWT secret `JOB_SIGNING_KEY` shared web↔worker), `NEXT_PUBLIC_TIER_MODE=full|tier-a`.

---

## 5. Locked decisions (do not re-litigate without user)

| ID | Decision |
|---|---|
| OQ-01 | GitHub **connect later**; repo local until then |
| OQ-02 | **KiCad `.kicad_pcb` first** (embedded stackup); Gerber+wizard second |
| OQ-03 | Injection: **`.cir` rewrite default + additive `.qsch` opt-in**; full `.qsch` rewire post-MVP |
| OQ-04 | Anonymous TTL sessions (default, privacy-friendly); accounts revisit at Phase 5 |
| OQ-05 | v1.0 = **power electronics** (commutation loops) |
| OQ-06 | **Open-core**: MIT engine + web app; hosted terms before v1.0; NOTICE.md hygiene |
| T-008 | **Vercel compatibility is mandatory** (web on Vercel; worker elsewhere) |
| — | Extraction default tier **B** (FastHenry2 + FasterCap) |
| — | Verification proxy **ngspice**; QSPICE = user-side step |
| — | Python backend (worker) + Next.js/TS frontend (Vercel) |

Open (intentionally undecided): access-model UI polish, exact report layout, marketing site, whether to publish to PyPI a `pcbparasitic` CLI (T-505).

---

## 6. Working rules for whoever continues (human or AI)

1. **One task per commit**, message starts with the task ID (`T-010: …`). Tick `plan.md` in the same commit.
2. **Never invent solver results.** Wire real subprocesses or label outputs "Tier A estimate". Every number in UI/report carries provenance (formula/solver, mesh, f₀, date) — this is the trust moat.
3. **Never modify uploaded user bytes in place.** Produce new artifacts; keep originals; deterministic ZIP; `manifest.json` of changes; full diff offered for download.
4. **No QSPICE binaries in repo/containers/Drive.** Users install it (Windows). Link: qorvo.com/design-hub → getqspice.com. Mention nominative use only ("for QSPICE®").
5. **Solver safety:** subprocess isolation, rlimits, no network, timeout, kill on overrun; on non-convergence → fall back Tier A with a loud banner, never silent downgrade.
6. **Passivity always audited** before emitting `parasitics.lib`; reject/flag otherwise.
7. **Security:** zip-bomb & path traversal guards; TTL-delete artifacts (default 24 h); signed URLs; IDOR tests; dependency scanning; `/security-review` (or SAST) before any release tag.
8. **License hygiene:** no copying skill text or GPL code into codebase; solvers via subprocess only; NOTICE.md updated when pinning deps.
9. **Vercel correctness:** web stays free of native deps (no python, no binaries in the Next.js bundle); worker Docker image ≤ 500 MB; document cold starts.
10. **Plan hygiene:** new tasks get new IDs (never renumber); decisions → Decision log; risks → risk register; milestones re-dated honestly.
11. **Fixtures:** use only permissively-licensed or synthetic fixtures in git. For snapshot tests of real `.qsch` files, prefer files from `QSpice-Circuits/Qspice-examples` (check each file's license note) or generate our own with QSPICE.
12. **Docs are code:** update `making.md` + Drive mirror whenever you change state.

---

## 7. Git & GitHub (when the connector is available)

Local state (as of writing): branch `main`, HEAD `3837d62` (+ uncommitted Vercel edits — this file, README, plan.md).

When GitHub connector works (or user pushes manually):
```bash
cd /home/user/pcb-parasitic-qspice
git remote add origin git@github.com:<USER>/pcb-parasitic-qspice.git   # or https
git push -u origin main
```
Then: create `develop` branch? Keep simple: trunk-based `main` + PR previews on Vercel. Add branch protection, required CI (T-010), secret scanning. Suggested private repo name: `pcb-parasitic-qspice` (owner decides; commercial-open-core → private until launch, or public MIT with issues/discussions).

---

## 8. Environment facts (this sandbox, 2026-11-22)

- Python **3.13.18**, Node **20.20.2**, npm **10.8.2**, git **2.47.3**, no gcc check run, no solvers installed (`ngspice`, `fasthenry2` absent) — install per Phase 2/3 (`apt-get install ngspice`, build FastHenry2 from source or use Windows binaries on the worker).
- `curl` works; GitHub raw reachable. `file` command misfires on `.qsch` (cosmetic).
- Google Drive connector: **enabled**; folder + files uploaded; use `upload_file` to add/update mirrors; use `update_file_content` on existing Doc files to refresh them in place.
- No GitHub connector (unsupported in Arena).
- Workspace root = `/home/user`; everything persistent lives under it.

Useful commands:
```bash
python3 - <<'EOF'
print(open('noise.qsch','rb').read(32))   # inspect any qsch
EOF
grep -c $'\xab' file.qsch                  # record count sanity
```

---

## 9. Immediate next steps (in order)

1. **Sprint 1 (done 2026-11-22)** — implemented + live-verified: FastAPI Tier A worker (`worker/`), Next.js workbench UI (`apps/web/`), `.cir` boundary-anchor injection, additive `.qsch` injection, HTML engineering report, CI skeleton, Docker/compose, screenshots in `docs/assets/`.
2. **Sprint 2 (done 2026-11-22)** — **Tier B PEEC field solver live**: `field.py`, `scripts/build-fasthenry.sh`, multi-stage `worker/Dockerfile`, tier plumbing through API/UI/report, 9 new tests, `docs/TIER-B.md`. Validated to 0.00 % (analytic DC R), +0.9 % (MIT reference), +7.7 % (straight trace vs microstrip). **Capacitance still Tier A — T-304 is blocked on licensing/64-bit issues, read its plan.md note first.**
2. **T-204** Gerber RS-274X/Excellon ingestion via gerbonara (`pip install gerbonara`) behind the same `analyze()` contract — unlocks non-KiCad boards.
3. **T-202 / T-103** QSPICE ZIP inventory + parse-error pointers in the UI (surface `file:line` for netlist errors).
4. **T-303** FastHenry2 spike (`git clone ediloren/FastHenry2`, build, run on probe-board SW loop; parse Zc matrix; compare vs Tier A — acceptance: |L_A − L_B| / L_B ≤ 15 % on fixture).
5. **T-406** ngspice verification gate inside the worker (`.op` + one `.tran`; hard-fail with rollback on failure) — `pip install ngspice`? (ngspice binary) — CI proxy for QSPICE.
6. **T-308** `parasitics.json` schema v1 + JSON Schema validation of worker output.
7. Keep Drive mirror current after each milestone; add dated ZIP snapshot before handing off.

---

## 10. Handoff checklist for the NEXT chat/AI (copy-paste this)

```
You are continuing "PCB Parasitic Engine for QSPICE".
1) Open the workspace; go to /home/user/pcb-parasitic-qspice. If missing, extract the Drive ZIP "pcb-parasitic-qspice-*.zip" (folder: PCB Parasitic Engine for QSPICE) into /home/user/.
2) Read making.md fully, then plan.md ("Progress log — 2026-11-22"). State the current HEAD (`git log --oneline -1`) before doing anything.
3) Implement the first unchecked task only. Follow "Working rules" in making.md §6.
4) Before ending: tick the task in plan.md, commit, and upload updated docs to the Drive folder (README.md, plan.md, making.md) with upload_file / update_file_content.
5) If anything is ambiguous: ASK the user. Never fabricate solver numbers, file formats, or test results.
```

---

## 11. Links

- Drive mirror folder: https://drive.google.com/drive/folders/1gCw61aLNj_gfCBfma3RrMhbTjHtA43b7
- QSPICE (Qorvo): https://www.qorvo.com/design-hub/design-tools/interactive/qspice · installer: https://getqspice.com/InstallQSPICE.exe
- QSPICE forums (file formats, CLI): https://forum.qorvo.com/c/qspice/
- QSPICE examples corpus (format specimens): https://github.com/QSpice-Circuits/Qspice-examples · https://github.com/KSKelvin-Github/Qspice
- FastHenry2: https://github.com/ediloren/FastHenry2 · FasterCap: https://github.com/ediloren/FasterCap · FastCap2: https://github.com/ediloren/FastCap2 · FastImp: https://github.com/ediloren/FastImp · https://www.fastfieldsolvers.com
- openEMS: https://www.openems.de · https://github.com/thliebig/openEMS-Project
- kiutils: https://github.com/mvnmgrx/kiutils · gerbonara: https://github.com/jaseg/gerbonara · KiCad pcbnew API: https://docs.kicad.org/10.0/en/pcbnew/
- Skills (see docs/SKILLS.md for full list + installs): https://github.com/anthropics/skills · https://github.com/vercel-labs/agent-skills · https://github.com/obra/superpowers · https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- Key papers: Ruehli 1974 (PEEC) · Kamon/White 1994 (Fasthenry) · Nabors/White 1991 (FastCap) · IPC-2141A · TU Ilmenau IEEE #9472438 · PCBParC (ResearchGate #254042181) — details in docs/RESEARCH.md

---

## 12. Definition of done (v1.0)

Upload QSPICE ZIP + KiCad board → pick power-loop net(s) → run Tier B extraction → download ZIP whose project simulates in QSPICE with visible parasitic R/L/M/C → PDF report with provenance & before/after overshoot delta — all on Vercel (Tier A preview) and on the worker (full fidelity), with CI green, Playwright golden path passing, and docs (README, making.md) current. Nothing ships below that bar.

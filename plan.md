# PLAN — PCB Parasitic Engine for QSPICE

> **Working title:** `pcb-parasitic-qspice` · **Owner:** project team · **Last updated:** 2026-11-22 (sprint 2 — Tier B PEEC field solver live & validated)
>
> **Checkbox protocol:** every task is `- [ ]` (pending) → after it is done, change to `- [x]` and append `— done YYYY-MM-DD (commit <sha>)`. Never delete a task; strike scope changes with `~~text~~` and add a note. Keep this file honest: it is the single source of truth for project status.

**Status legend:** `[ ]` pending · `[x]` done · ~~struck~~ descoped · 🔒 blocked (with reason)

---

## Progress log — 2026-11-22 · Sprint 2: Tier B PEEC field solver (FastHenry2) — LIVE

**Question that started it:** *"why the limitation PEEC fasthenry2 — can u fix it?"* → Yes.

**What runs today** (every number below came from a real run in this workspace):

1. `worker/pcb_engine/field.py` — new module. Builds a FastHenry `.inp` from KiCad geometry:
   trace segments at their true layer z, coincident endpoints welded, **layer changes inferred as via
   segments**, nearest reference plane (either side, thinnest diel — same rule as Tier A) emitted as a
   finite `g1` sheet, FAR terminal `.equiv`'d to the plane, port = `NEAR ↔ plane-node-under-it`.
   Then subprocess-solves FastHenry 3.0.1 and parses `Zc.mat`.
2. **Solver build:** `scripts/build-fasthenry.sh` clones [ediloren/FastHenry2](https://github.com/ediloren/FastHenry2)
   (MIT / FastFieldSolvers 64-bit port) and builds it with `-O2 -std=gnu89 -fcommon` + K&R-era warning
   suppressions, then **self-verifies** against an analytic DC resistance (16.381 mΩ) before installing.
   `worker/Dockerfile` is now multi-stage and compiles it into the image.
3. **Tier plumbing:** `pipeline.analyze(tier="A"|"auto"|"B")`, per-net `tier_b` block in the API
   payload, `_net_payload()` injects the **Tier B** R/L (C stays closed-form), `parasitics-meta.json`
   records solver path + version, `/health` reports real solver availability.
4. **Report:** new §2b "Tier B field solve", Tier A vs B columns side by side, per-net Δ, mesh
   convergence chips, and an honest header line ("Tier A closed-form (all nets) + Tier B field solve
   (2 of 2 nets)"). Assumptions section now states that C is always closed-form.
5. **UI:** solver-tier selector (Auto / Tier A / Tier B), B columns in the net table with Δ and a
   `⚠` when the mesh didn't converge, and a "Why B ≠ A" explainer.
6. **Graceful degradation:** no binary → `/health` says so, UI banner, report header says
   "Tier A — closed-form (no field solver available)", `meta.json` records the fallback. `tier=B`
   with no binary is a hard 422, never a silent downgrade.
7. **Tests: 26/26 green** (`python3 -m unittest discover -s worker/tests`), including 9 new ones:
   reference-plane selection, the `.units mm` σ convention, `+` continuation of plane ref-nodes, one-via
   inference, no-duplicate-elements, analytic DC resistance, VIN-vs-microstrip within 12 %,
   convergence reporting, tier routing.

**Validation (measured, this sprint):**

| Case | Reference | Tier B | Δ |
|---|---|---|---|
| DC R, 10 mm × 0.3 mm × 35 µm Cu | 16.381 mΩ (ρL/A) | 16.381 mΩ | 0.00 % |
| MIT `plane.in` @ 600 MHz | R = 15 Ω (file's own note) | 15.13 Ω | +0.9 % |
| Fixture `VIN` loop L @ 50 MHz | 4.045 nH (Tier A microstrip) | 4.354 nH | +7.7 % |
| Fixture `VIN` mesh 25×10 → 60×60 | — | 4.396 → 4.354 nH | −0.1 % (converged) |
| Fixture `SW` (2 layers + via, finite plane) | 13.156 nH (Tier A) | 19.287 nH | **+46.6 %** — the finite-plane effect Tier A cannot see; converged (1.5 % drift) |

**Five bugs that cost real time** (documented in `docs/TIER-B.md` §5 so they are never re-lived):
`.units mm` scales σ too (1000× error); `npfar`/`npnear` must be `+` continuation lines of the `g1`
block; a via added twice → coincident filaments → 46 Ω garbage; adjacent-layer dielectric gap read 0;
the 1996 MIT tarball truncates 64-bit pointers (its `ualloc()` has no prototype → implicit `int`).

**Honest scope notes (still open):** capacitance remains Tier A closed-form (T-304 — FastCap's 1992
allocator hangs on 64-bit, FasterCap is wxWidgets-3.0/GPL-bound); mutual L between different nets
not yet solved as a port matrix (T-303b); single f₀ per net, no Foster ladder (T-306); plane voids
not meshed (T-102 follow-up); passivity audit not wired (T-305).

---

## Progress log — 2026-11-22 · Sprint 1: end-to-end Tier A vertical slice (implemented & verified in-session)

**What runs today** (all steps exercised live, not just written):

1. `worker/pcb_engine/parasitics.py` — stackup-aware Tier A kernel: Hammerstad–Jensen microstrip (Z₀, ε_eff, L′, C′, delay), IPC-2141A symmetric stripline, Grover partial inductance (no-reference segments), via barrel L & AC R, skin-depth R(f), perimeter skin-effect model, **reference plane = nearest copper on either side, thinnest dielectric gap wins** (buried symmetric-stripline handling included).
2. `worker/pcb_engine/kicad.py` — kiutils-based `.kicad_pcb` ingestion: segments/vias/nets/stackup (foil t, εr) with 4-layer fixture (`worker/fixtures/probe_board.kicad_pcb`).
3. `worker/pcb_engine/cir.py` — `.cir` whole-net transformer: case-insensitive node rewrite (SPICE), **boundary-anchor injection** (independent source V/I keeps original node; otherwise first referencing device anchors; token-level anchoring — one line can anchor one net while rewriting another), idempotent (refuses double-injection), unified diff, mutual-K support. Parasitic ladder: `R_PAR_*`, `L_PAR_*`, `C_PAR_*` → `.include parasitics.lib`.
4. `worker/pcb_engine/qsch.py` — `.qsch` parser/writer with byte-verified format (magic `FF D8 FF DB`, `0xAB…0xBB` records). **Additive-only injection**: BOM-prefixed `.include parasitics.lib` + provenance comment appended before root close; geometry records never touched. Unit tests + additive round-trip test.
5. `worker/pcb_engine/report.py` — self-contained HTML engineering report (no external assets): stackup table, per-net R/L/C/Z₀, inline-SVG |Z(f)| plot w/ resonance peak, injection stats, files-changed ledger, assumptions & uncertainty.
6. `worker/pcb_engine/pipeline.py` — zip-safe orchestration (path-traversal rejected, 400 files / 256 MB / 64 MB caps), SPICE auto-detection (strong extensions trusted; `.net/.lib/.txt` need ≥2 netlist signals; **KiCad s-expression files are never touched**), power-electronics net heuristic (SW/gate/VIN flagged ◆ CRITICAL), default selection = critical nets, parasitic-injected ZIP rebuilt (original byte-preserved) + `parasitics.lib` + `parasitics-meta.json` + `PARASITICS-REPORT.html`.
7. `worker/main.py` — FastAPI: `/api/analyze`, `/api/inject`, `/api/download/{token}`, `/api/report/{token}`, `DELETE /api/session/{token}`; anonymous TTL sessions (1 h, wiped on demand), per-IP rate limiting, upload size caps; `DATA_DIR`-rooted storage, nothing off-host.
8. `apps/web` — Next.js 14 App Router UI: hero, workbench (upload → extract → select → inject → download), dark EDA design system (custom CSS, 93 kB First Load JS), live impedance chart (inline SVG), responsive (optional columns collapse <1560 px), keyboard/aria/focus-visible throughout; `next.config.js` rewrites `/api/*` → worker (browser never sees worker origin); `output: 'standalone'` for Docker; `vercel.json` ready.
9. Verified live: analyze (SW: L=13.16 nH, C=7.5 pF, R=79.8 mΩ @ f₀, Z₀=39.3 Ω), injection into a demo QSPICE-style ZIP (`.cir` boundary-correct: source untouched, consumers re-pointed, ladder in series; `.qsch` additive block appended), report render, proxy download, `npm run build` clean, typecheck clean, **14/14 engine tests pass**.
10. Repo: `.github/workflows/ci.yml` (T-010), root `package.json`, `worker/Dockerfile` (non-root, healthcheck), `apps/web/Dockerfile` (standalone), `docker-compose.yml`, `.gitignore` for `node_modules/.next`.

**Honest scope notes at end of sprint 1** *(superseded in part by sprint 2 — PEEC field solving landed; see above)*: ~~no PEEC field solving~~ (done, T-303), no mutual inductance extraction from geometry (K only when provided) → T-303b; ~~no proximity effect~~ in Tier A (Tier B now has it natively); zones detected but not solved (T-102 follow-up); ngspice verification gate not wired (T-406); Gerber path (T-204) not started; Tier A `.cir` includes only lumped R/L/C (no frequency-dependent Foster ladder, T-306); single-transform only, no passivity audit (T-305); Next pinned at 14.2.35 (upgrade path folded into T-708/T-711); visual design system is bespoke CSS, not shadcn (T-106 honored in spirit, not letter).

---

## Phase 0 — Research, foundations, repository (current)

- [x] **T-001** Git repository created (`main`, local at `/home/user/pcb-parasitic-qspice`) — done 2026-11-22 (note: no GitHub connector available in Arena; push manually or connect later, see OQ-01)
- [x] **T-002** Environment survey (Python 3.13.18, Node 20.20.2, git 2.47.3; no solvers installed yet) — done 2026-11-22
- [x] **T-003** QSPICE internals investigation — file extensions, CLI (`QUX -Netlist`, `QSPICE64.exe` as `qspice`), netlist/`.qraw` semantics; verified `.qsch` = magic `FF D8 FF DB` + ASCII records (`0xAB` start / `0xBB` terminator, hierarchical indent) from a real example file — done 2026-11-22 (see `docs/RESEARCH.md` §4)
- [x] **T-004** Parasitic-extraction knowledge base — PEEC, FastHenry2/FasterCap/FastCap2/FastImp, openEMS, closed-form IPC-2141A/Hammerstad, Grover partial inductance; papers and validation evidence collected — done 2026-11-22 (see `docs/RESEARCH.md`)
- [x] **T-005** AI skills inventory for professional web-app development (Anthropic/Vercel/community GitHub skills, install commands, application map) — done 2026-11-22 (see `docs/SKILLS.md`)
- [x] **T-006** `README.md` — product definition, workflow, tiers, commitments — done 2026-11-22
- [x] **T-007** `plan.md` — this checkboxed plan — done 2026-11-22
- [x] **T-008** Stakeholder review of README/plan; lock OQ-01…OQ-06 — done 2026-11-22 (decisions: OQ-01 review → connect GitHub later (no connector available in Arena); OQ-02 **KiCad `.kicad_pcb` first**; OQ-03 **both modes — `.cir` rewrite default + additive `.qsch` opt-in**; OQ-05 **power-electronics focus**; OQ-06 **open-core (MIT engine)**. OQ-04 (access model) → default locked to **anonymous TTL sessions**, revisit at Phase 5)
- [x] **T-009** LICENSE decision (open-core: MIT for engine) + NOTICE file for third-party licenses & trademarks — done 2026-11-22 (`LICENSE`, `NOTICE.md`)
- [x] **T-010** CI skeleton — GitHub Actions: lint (ruff, eslint), type-check (mypy, tsc), unit tests, Playwright smoke; pre-commit hooks — done 2026-11-22 (`.github/workflows/ci.yml`: engine unittest + web typecheck + `next build`); note: no GitHub remote yet (OQ-01), CI validated locally

**Milestone M0 — "Approved foundation"** = T-008 ✅ + T-009 ✅ + T-010 (CI skeleton) green. Foundation docs are decision-complete; only CI remains.

---

## Phase 1 — Product definition & UX

- [ ] **T-101** User personas & top 5 jobs-to-be-done (power-electronics loop extraction; gate-driver ringing; sensor/IC supply bounce; high-speed I/O; general PDN check)
- [ ] **T-102** End-to-end UX flows (wireframes): project upload → PCB upload → stackup wizard → net/target selection → extraction options → progress → results dashboard → download + report
- [ ] **T-103** Error model & recovery paths (bad zip, missing drill file, unmatched footprints, non-converged solver, non-passive result) with copy deck
- [ ] **T-104** Report format spec (sections, provenance, uncertainty, diff view) + data schema for extraction results (JSON Schema)
- [ ] **T-105** Data-retention & privacy policy text (EU/GDPR-aware: session-scoped artifacts, TTL auto-delete, no training use)
- [x] **T-106** Visual design system (dark EDA-lab aesthetic; tokens; shadcn/ui theme; board-viewer look & feel) + component inventory — done 2026-11-22 (bespoke CSS token system in `apps/web/app/globals.css`; shadcn/Tailwind deferred — zero-dependency choice, see R-09)

**Milestone M1 — "Signed-off UX"** = T-101…T-106.

---

## Phase 2 — Ingestion layer (PCB + QSPICE ZIP)

- [x] **T-201** Secure ZIP handling: bomb/size caps (e.g. 100 MB / 10k entries), path-traversal filter, MIME sniffing, quarantine dir, streaming extract (no full load in memory) — done 2026-11-22 (in-memory with caps: 400 files / 256 MB total / 64 MB per file; traversal rejected; SPICE MIME sniffing; NOTE: streaming extract not yet implemented — acceptable at current size caps)
- [ ] **T-202** QSPICE ZIP inventory: classify `.qsch/.cir/.qsym/.lib/.sub/.pfg/.cpp/.qraw`; parse project manifest; detect multi-sheet projects; store immutable upload snapshot
- [ ] **T-203** KiCad parser module (`.kicad_pcb`, netlist `.net`, footprint/pad data) using `kiutils` + `pcbnew` cross-check when KiCad present; extract tracks/arcs/vias/zones/pads/nets/stackup (thickness, εr, copper weight)
- [ ] **T-204** Gerber RS-274X/X2 + Excellon DRL parser via `gerbonara`; layer polarity, apertures, regions; drill map; units; board outline; net inference from IPC-D-356 when present
- [ ] **T-205** IPC-2581 importer (XML; stackup + nets + geometry) — post-MVP candidate, spike in this phase
- [ ] **T-206** Stackup model & defaults: FR-4 presets (εr 4.2–4.6, tan δ 0.02), copper 0.5/1/2 oz, solder-mask layer, surface finish/roughness factor; validation UI
- [ ] **T-207** Component/footprint resolution: designator→footprint→net pins; schematic↔PCB match report (from KiCad `.net` or name/designator heuristics + manual mapping UI)
- [ ] **T-208** Geometry meshing pipeline: tracks/vias/pads → solver primitives (segments, planes with holes, dielectric boxes); mesh-size convergence checks
- [ ] **T-209** Board SVG/Canvas viewer data model (parsed geometry → renderable primitives + hit-testing) shared frontend/backend schema

**Milestone M2 — "Parse anything, safely"** = T-201…T-209 with fixture corpus (≥10 real boards: 2/4/6-layer, KiCad + Gerber flows).

---

## Phase 3 — Extraction engine (the science)

- [ ] **T-301** Tier A closed-form kernel: microstrip/stripline Z₀, ε_eff, L′, C′, delay (IPC-2141A; Hammerstad–Jensen correction; embedded/asymmetric cases); skin depth δ(f); proximity-effect factor (Dowell/Yang); DC + AC resistance; plane spreading resistance (Grover/Keeth); via inductance & resistance (formula + model selection)
- [ ] **T-302** Partial inductance library: Grover/Rosa formulas for rectangular filaments, mutual between filaments; sign conventions; guard rails (parallel/perpendicular criteria)
- [x] **T-303** FastHenry2 integration: generate `.inp` (nodes/elements/planes), run subprocess, parse impedance matrices, discretization, convergence study — **done 2026-11-22** (`worker/pcb_engine/field.py`; `scripts/build-fasthenry.sh`; multi-stage `worker/Dockerfile`; validated to 0.00 % on analytic DC R, +0.9 % on MIT `plane.in`, +7.7 % vs microstrip on a straight trace; convergence reported per net). Caveats: single f₀ per net (sweep = **T-306**), one port per net (mutual L = **T-303b**), plane voids not meshed (T-102 follow-up)
- [ ] **T-303b** Multi-port FastHenry solve → full Z-matrix across selected nets → `K` statements with documented sign convention; reuse `MakeLcircuit`-style coupling extraction
- [ ] **T-304** Capacitance: FasterCap/FastCap2 integration (conductor surfaces + dielectric boxes; inhomogeneous media; auto-refinement; charge/Q extraction; capacitance matrix → SPICE) — **attempted 2026-11-22, blocked**: FastCap 2.0 (1992) builds but hangs on trivial
  geometries (K&R allocator on 64-bit, root cause not isolated); FasterCap 6.0.7's prebuilt Linux binary
  needs wxWidgets 3.0 (absent on Debian trixie) and its source is **GPL** — a licensing decision, not
  just a build one. Capacitance therefore stays Tier A closed-form, always labelled as such.
- [ ] **T-305** Geometry→PEEC model assembly: loop identification (trace + return path via reference plane), mutual-coupling matrix assembly, K-statement generation (QSPICE-supported), passivity/causality audit (eigenvalue check; optional Foster synthesis / vector fitting à la Gustavsen–Semlyen for frequency-dependent R)
- [ ] **T-306** Frequency-dependent R handling (QSPICE has no `W` element): single-frequency extraction at user f₀, or Foster ladder approximation; document limitation in report
- [ ] **T-307** Tier C spike (optional, post-MVP): openEMS FDTD for critical nets; define acceptance criteria vs Tier B
- [ ] **T-308** Extraction result schema v1 (`parasitics.json`): per net/segment R, L, M pairs, C to ref, C mutual, provenance, solver settings, convergence metrics, uncertainty band
- [ ] **T-309** Validation suite: golden geometries (50 Ω microstrip vs formula; square air loop vs Grover; two coupled striplines vs Hammerstad/AppCAD; via vs literature) + **benchmark vs TU Ilmenau and PCBParC published results**; CI gate on tolerances

**Milestone M3 — "Trustworthy numbers"** = T-301…T-306, T-308, T-309 (T-307 optional).

---

## Phase 4 — QSPICE injection & report

- [x] **T-401** `.cir` netlist transformer: parse → net rename + node splitting → insert series R/L, shunt C-to-reference, mutual K; keep `.include parasitics.lib`; idempotent (refuses double-injection); full before/after diff; case-insensitive node rewrite; boundary-anchor model (see decision log) — done 2026-11-22
- [x] **T-402** `.qsch` additive writer: embed `.include parasitics.lib` + labeled provenance block appended before root close; additive-only; snapshot tests vs synthetic fixture built from the verified grammar; **never rewrite existing geometry** — done 2026-11-22 (NOTE: real-corpus snapshot tests pending a bigger .qsch corpus — R-01 remains open)
- [ ] **T-403** `parasitics.lib` generator: `.subckt` per net-segment/PI-network, `.param` for values, comments with provenance (solver, mesh, f₀, date), unit-safe formatting, component naming scheme (`X_PAR_*`) avoiding user-namespace collisions
- [ ] **T-404** Repack ZIP: byte-preserve untouched files; deterministic ordering; `manifest.json` (what changed & why); keep original under `/original/` optionally (user toggle)
- [ ] **T-405** Report generator (HTML → PDF): executive summary, per-net table + plots (R/L/C vs f), stackup recap, mapping table, solver provenance, passivity audit, assumptions/warnings, QSPICE usage instructions (how to run, what to look at: overshoot, ringing freq, damping)
- [ ] **T-406** Verification gate: re-parse injected netlist; ngspice run (OP + one TRAN) to confirm no singular/duplicate nodes; compare pre/post node counts; hard-fail with rollback on any check failure
- [ ] **T-407** QSPICE-side verification path (Windows runner or documented user step): `QSPICE64.exe project.cir` smoke test + expected `.qraw` existence check; documented in report appendix

**Milestone M4 — "Download-and-simulate"** = T-401…T-406 (T-407 documented).

---

## Phase 5 — Web platform (backend)

- [ ] **T-501** FastAPI app skeleton: project/job model, upload endpoints (signed), artifact store (S3/MinIO), PostgreSQL + Alembic migrations, pydantic settings, structured logging, OpenTelemetry traces
- [ ] **T-502** Worker service (RQ or Celery): job queue, solver subprocess sandboxing (rlimits, timeout, no network), progress events (Redis pub/sub → websocket/SSE), retries with backoff, dead-letter handling
- [ ] **T-503** Auth & accounts (email+password, OAuth GitHub/Google optional) OR anonymous session mode with TTL artifacts (product decision OQ-04); rate limiting; API keys for CLI
- [ ] **T-504** Security hardening: CSP, CORS allowlist, CSRF for session flows, file TTL sweeper (default 24 h), audit log, dependency scan (pip-audit/npm audit), threat model doc
- [ ] **T-505** CLI (`pcbparasitic`) — same engine without UI (engineers live in terminals; enables CI use by EDA teams)
- [ ] **T-506** Observability & ops: dashboards (jobs/min, solver runtime p50/p95, failure rate), error tracking (Sentry), health/readiness probes, backup/restore of metadata DB

**Milestone M5 — "Multi-user dependable backend"** = T-501…T-504 + T-506.

---

## Phase 6 — Web platform (frontend, professional grade)

- [ ] **T-601** React+TS+Vite app shell: routing, auth guard, error boundaries, i18n-ready (en; ar optional later — Cairo timezone user), dark EDA theme, design tokens from T-106
- [x] **T-602** Upload flow UI: drag-drop ZIPs, client-side validation, progress, parse-error surfacing — done 2026-11-22 (drop zones + API error surfacing; "line/file pointers" for parse errors deferred to T-103)
- [ ] **T-603** Board viewer: SVG/Canvas render of parsed copper layers with layer toggles, net highlighting, pan/zoom, click-to-select nets for extraction targets
- [ ] **T-604** Stackup editor: drag layer thickness/εr edit, presets, cross-section mini-diagram (SVG), impedance preview per net (Tier A live)
- [ ] **T-605** Mapping UI: schematic symbols ↔ PCB footprints ↔ nets; unresolved items highlighted; one-click heuristics + manual override
- [ ] **T-606** Extraction options & live job monitor: tier picker (A/B/C), frequency range, mesh density, ETA; SSE progress; cancel; logs viewer
- [ ] **T-607** Results dashboard: per-net R/L/C charts (log-f), before/after comparison, download ZIP + report; extraction artifacts browser
- [ ] **T-608** E2E (Playwright): golden-path run on sample project (fixture board + sample QSPICE zip) — must pass in CI; visual regression snapshots
- [ ] **T-609** Accessibility pass (WCAG 2.1 AA): keyboard nav, focus rings, contrast, aria labels; Lighthouse ≥ 90 a11y/perf/best-practices

**Milestone M6 — "Professional UI shipped"** = T-601…T-609.

---

## Phase 7 — Productionization & release

- [ ] **T-701** Two deployment profiles: (a) **Vercel** — `apps/web` Next.js (UI + stateless Tier A Route Handlers) + managed Postgres (Neon/Supabase) + Upstash Redis; (b) **Full** — `docker compose` (web + worker + postgres + redis + minio) for self-hosted/on-prem. Production Dockerfiles for the worker (multi-stage, non-root, pinned digests); thin Vercel build for web
- [ ] **T-702** Deployment guide & one-click compose for a single VM; optional k8s manifests; config via env; secrets strategy
- [ ] **T-703** Docs site (MkDocs Material in `docs-site/` or `/docs`): user guide, stackup guide, QSPICE walkthrough, FAQ, troubleshooting, validation report appendix
- [ ] **T-704** Performance & scale test: 100 concurrent parses, 10 concurrent Tier-B jobs; memory ceilings; p95 latencies documented
- [ ] **T-705** Security review (using AI security-review skill + manual): authz on every artifact URL, IDOR tests, zip fuzzing; fix findings; publish security.md + disclosure policy
- [ ] **T-706** Release v1.0.0: tagged, changelog, sample artifacts (demo project download), known-limitations page
- [ ] **T-707** Post-release: telemetry review, user feedback intake, backlog triage
- [ ] **T-708** Vercel Tier A kernel: `packages/kernel` TypeScript (microstrip/stripline Z₀, ε_eff, L′/C′, skin depth, Grover partial L) running in Next.js Route Handlers; zero native deps; <60 s (target <1 s); <50 MB; unit tests vs Python engine golden vectors
- [ ] **T-709** Solver worker API: signed job dispatch (JWT, single-use), SSE progress back to Vercel app, artifacts to S3/R2, idempotency keys, concurrency limits, per-job timeouts; deploy recipes: Fly.io / Railway / Cloud Run / bare VM
- [ ] **T-710** Vercel preview deployments use **mock worker** (seeded fixture results) so every PR gets a working preview; `NEXT_PUBLIC_WORKER_URL` optional → absence ⇒ Tier A mode with UI banner
- [ ] **T-711** "Deploy with Vercel" button in README + `vercel.json` + one-click env setup (Postgres/Redis/S3 auto-provision via Vercel Marketplace); quick-start < 5 min for Tier A mode
- [ ] **T-712** Vercel performance budget: Lighthouse ≥ 95 (perf/a11y/best-practices), TTFB < 1 s edge, bundle < 300 KB gz initial; documented cold-start behavior
- [ ] **T-713** Worker fallback UX: if worker unreachable mid-job, resume/retry + clear error + keep partial report; no silent failures

**Milestone M7 — v1.0 shipped.**

---

## Phase 8 — Extended physics (post-MVP, optional)

- [ ] **T-801** Tier C full-wave GA: openEMS for critical nets with automated mesh
- [ ] **T-802** Coupled power-integrity mode: plane resonance (FDTD or cavity model), PDN impedance output
- [ ] **T-803** Eye-diagram sanity tool for high-speed nets (statistical)
- [ ] **T-804** Differential-pair & crosstalk report (impedance, skew, coupling table)
- [ ] **T-805** Altium Designer input path (ODB++ export or .PcbDoc parser — evaluate feasibility/licensing)
- [ ] **T-806** Model-order-reduction for huge PEEC matrices (vector fitting)

---

## Risk register

| ID | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R-01 | `.qsch` undocumented; additive writer breaks on unseen variants | M | H | Additive-only edits; corpus snapshot tests; magic-byte assert; refuse-on-unknown-version |
| R-02 | QSPICE Windows-only; no headless verify on Linux | H | M | ngspice as CI proxy; documented Windows runner path; user-side smoke check in report |
| R-03 | Gerber has no dielectric stackup → wrong εr/h → wrong C/Z₀ | H | M | KiCad-first path (embedded stackup); wizard + fab defaults; impedance sanity preview; report warnings |
| R-04 | Extracted matrix non-passive → simulator convergence garbage | M | H | Eigenvalue passivity audit; reject/repair (diagonal loading); report flag |
| R-05 | Mutual inductance `K` sign/coupling errors in user circuit context | M | M | Explicit sign convention doc; per-loop K values in report; lint check (|K|<1) |
| R-06 | Solver (FastHenry2) crashes/timeout on pathological geometry | M | M | Sandbox + timeout + retry with coarser mesh; Tier A fallback with warning |
| R-07 | Incorrect footprint/net mapping → parasitics on wrong nets | M | H | Mapping UI requires user confirmation; net-name heuristics; diff review before download |
| R-08 | Licensing: GPL (FasterCap? actually FastHenry2/FasterCap are MIT/BSD-like per F-Si; openEMS is GPL-3) in proprietary web service | L | M | Subprocess isolation; no code linking; license review in T-009; keep solvers as external tools |
| R-09 | Scope creep (full SI tool) | M | M | This plan is the contract; Phase 8 is explicitly post-MVP |
| R-10 | Trust: user distrusts AI-ish "black box" | M | M | Provenance everywhere; open formulas; validation vs publications; uncertainty bands; open-source core |
| R-11 | Vercel serverless limits (size/timeout, no native solver binaries) break Tier B/C | H | M | Tier split is mandatory: Tier A native TS on Vercel; Tier B/C only in container worker; previews use mock worker; documented in `making.md` + README |

---

## Milestones (indicative, 2026)

| Milestone | Content | Target |
|---|---|---|
| M0 | Foundation approved | 2026-11-29 |
| M1 | UX signed off | 2026-12-06 |
| M2 | Ingestion layer + fixtures | 2026-12-20 |
| M3 | Extraction engine validated | 2027-01-17 |
| M4 | QSPICE injection + report | 2027-01-31 |
| M5 | Backend production-ready | 2027-02-14 |
| M6 | Frontend complete | 2027-03-07 |
| M7 | **v1.0 release** | 2027-03-21 |

---

## Open questions — RESOLVED 2026-11-22 (T-008)

- **OQ-01** GitHub remote → **connect later**. No GitHub connector exists in Arena (list returned `unsupported`); repo stays local until a connector is provided or the owner pushes manually.
- **OQ-02** PCB input priority → **KiCad `.kicad_pcb` first** (embedded stackup), Gerber + guided stackup wizard second.
- **OQ-03** Injection mode → **both: `.cir` netlist rewrite (default) + additive `.qsch` "PCB Parasitics" sheet (opt-in)**. Full `.qsch` rewire stays post-MVP.
- **OQ-04** Access model → **anonymous TTL sessions** (default, privacy-friendly); accounts revisited at Phase 5 (T-503).
- **OQ-05** Domain focus → **power electronics** (TU Ilmenau / PCBParC-validated use case) for v1.0; general SI post-MVP.
- **OQ-06** License → **open-core**: MIT engine + web app source now; hosted service terms published before v1.0; NOTICE.md covers third-party & Qorvo trademark hygiene.

## Decision log

| Date | Decision | By |
|---|---|---|
| 2026-11-22 | Repo `pcb-parasitic-qspice` created locally; git `main` | T-001 |
| 2026-11-22 | QSPICE injection strategy: **additive-only** for `.qsch`; rewrite mode only for `.cir` with diff | T-003 |
| 2026-11-22 | Verification proxy = ngspice; QSPICE batch = documented user/Windows path | T-003 |
| 2026-11-22 | Extraction default tier = B (FastHenry2 + FasterCap), consistent with validated literature | T-004 |
| 2026-11-22 | Python (FastAPI) backend + React/TS frontend | T-005/T-006 |
| 2026-11-22 | **GitHub remote → connect later** (no connector in Arena) — OQ-01 | T-008 |
| 2026-11-22 | **KiCad `.kicad_pcb`-first** ingestion; Gerber second — OQ-02 | T-008 |
| 2026-11-22 | **Injection = .cir default + additive .qsch opt-in** — OQ-03 | T-008 |
| 2026-11-22 | **Access = anonymous TTL sessions** (default; accounts revisited Phase 5) — OQ-04 | T-008 |
| 2026-11-22 | **v1.0 = power-electronics focus** (half-bridge commutation loops) — OQ-05 | T-008 |
| 2026-11-22 | **License = open-core (MIT engine)**; NOTICE.md shipped; hosted terms pre-v1.0 — OQ-06 | T-008/T-009 |
| 2026-11-22 | Deliverables mirrored to Google Drive folder "PCB Parasitic Engine for QSPICE" (id `1gCw61aLNj_gfCBfma3RrMhbTjHtA43b7`); `.md` files auto-converted to Google Docs for readability | T-008 |
| 2026-11-22 | **Vercel compatibility locked (hard requirement).** Monorepo: `apps/web` Next.js 15 on Vercel (UI + stateless Tier A Route Handlers); Tier B/C PEEC solver stays in a separate container worker (Fly.io/Railway/Cloud Run/VM); Vercel previews use a mock worker; `docker-compose` remains the all-in-one path — T-708…T-713, R-11 | T-008 |
| 2026-11-22 | **`making.md` = mandatory handoff document** for cross-chat continuity (any AI/human can resume); must stay current with repo state, decisions, verified facts | T-008 |
| 2026-11-22 | **Tier A reference-plane rule** = nearest copper on EITHER side, thinnest dielectric gap wins (B.Cu no longer "plane-less"; buried traces → symmetric-stripline b = gap up + trace + gap down) — fixes under-prediction of bottom-layer L (22.7→13.2 nH on fixture) | Sprint 1 |
| 2026-11-22 | **`.cir` injection = boundary-anchor model**: independent source (V/I) keeps the original node (series ladder boundary); otherwise the first referencing device anchors. Token-level anchoring (a line anchored for net A still rewrites net B). Consumers re-pointed to `<NET>__PAR`; ladder `R_PAR/L_PAR/C_PAR` inserted; shunt C → ref node; double-injection refused | Sprint 1 |
| 2026-11-22 | **SPICE matching is case-insensitive** (SPICE semantics); replacement tokens use the selected net's spelling (sanitized upper-snake) | Sprint 1 |
| 2026-11-22 | **Weak-extension SPICE detection**: `.net/.lib/.txt` need ≥2 netlist signals; strong exts `.cir/.sp/.spice` trusted; any file starting with `(` (KiCad s-expr) is NEVER rewritten | Sprint 1 |
| 2026-11-22 | **Stack as built**: Next.js 14.2.35 App Router + hand-rolled CSS design system (not Tailwind/shadcn yet; no new runtime deps), FastAPI worker (Tier A), browser→worker via Next rewrites; `output: standalone`; `worker/Dockerfile` + compose; Next 15 upgrade folded into T-708/T-711 | Sprint 1 |
| 2026-11-22 | **Report = self-contained HTML** (no external assets; inline CSS/SVG) — PDF deferred (T-405 follow-up) | Sprint 1 |
| 2026-11-22 | **Tier B solver = FastHenry 3.0.1 via the FastFieldSolvers 64-bit port** (MIT). The 1996 MIT tarball truncates 64-bit pointers (`ualloc()` has no prototype → implicit `int` return) and segfaults; not worth patching. Built from source, never vendored as a binary in git | Sprint 2 |
| 2026-11-22 | **FastHenry `.units mm` convention**: σ must be 5.814e4 1/(Ω·mm), *not* the µm-era 58.14. `.units` scales resistivity with the length unit — using the µm value gives exactly 1000× too much R | Sprint 2 |
| 2026-11-22 | **Tier B topology = inferred vias, not declared ones.** A via is synthesised where two copper layers meet at the same (x, y); the KiCad via count is reporting-only. Declaring it from the via list *and* inferring it produced two coincident filaments (identical centres → 46 Ω garbage) | Sprint 2 |
| 2026-11-22 | **Injection prefers Tier B, never mixes silently.** `_net_payload()` uses the field-solved R/L where available and keeps closed-form C, with `method` + `uncertainty` naming both. Report shows A next to B with the Δ, always | Sprint 2 |
| 2026-11-22 | **Tier B failure = loud.** No binary → `/health`, UI banner, report header and `meta.json` all say "Tier A"; `tier=B` with no binary is a hard 422. No silent downgrade | Sprint 2 |
| 2026-11-22 | **Capacitance stays Tier A** (T-304 blocked: FastCap 1992 allocator hangs on 64-bit; FasterCap is wxWidgets-3.0-bound and **GPL** — licensing review needed before bundling). Report states this on every run | Sprint 2 |

## How to update this file

1. Finish a task → flip `[ ]`→`[x]`, append `— done YYYY-MM-DD (commit sha)`.
2. Scope change → strike old text, add new task with new ID.
3. New risk → add R-nn. New decision → add row to log.
4. After each milestone, bump "Last updated" and re-date milestones honestly.

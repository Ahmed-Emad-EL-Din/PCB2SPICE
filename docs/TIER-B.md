# Tier B — PEEC field solving with FastHenry2

> **Status: LIVE (2026-11-22).** Magnetostatic L/R for every selected net, with a real finite
> reference plane, proximity effect, via loops and current crowding. Capacitance is still
> closed-form (see §5).

## 1. Why a field solver at all

The closed-form kernel (Tier A) maps each trace segment to a microstrip or stripline
cross-section and multiplies by length. That is a good first-order answer, but it bakes in one
assumption that is *never* true on a real board: **an infinite copper plane directly beneath the
trace, for the entire length of the run.**

Real boards break that assumption in three ways:

| What is actually there | What Tier A does | What it costs you |
|---|---|---|
| A **finite** plane that ends | Assumes it continues forever | Return current is forced to spread; loop L rises |
| A **layer change through one via** | Sums two independent microstrips | The whole return current must funnel through one barrel |
| **Neighbouring** copper carrying its own current | Ignores coupling | Proximity effect pushes current to the trace edges: R rises 15–40 % at HF |

Tier B replaces the formula with geometry. It builds the actual mesh — every segment, every via,
the plane as a discretized sheet — and solves the magneto-quasistatic system.

## 2. What it does, concretely

```
KiCad .kicad_pcb
      │
      ▼  kicad.parse_board_file()            (segments, vias, layers, stackup)
      │
      ▼  field.build_fasthenry_input()        ← topology construction (the tricky part)
      │     • trace segments on their real layer, z = copper mid-plane
      │     • coincident endpoints welded into one node
      │     • two layers meeting at the same (x,y) → one vertical via segment
      │     • nearest copper plane (either side, thinnest gap — same rule as Tier A)
      │       emitted as a finite `g1` sheet extending 5 mm past the net's bbox
      │     • FAR terminal `.equiv`'d to the nearest plane node (loop closed)
      │     • port = `.external NEAR plane_node_under_it`
      │
      ▼  FastHenry 3.0.1                     (MIT, 64-bit port, 2012)
      │     mesh → filaments → MNA → multipole GMRES at f₀
      │
      ▼  Zc.mat → Z = R + jωL
      │
      ▼  field.convergence_check()           (20 → 30 → 45 cells across the short edge)
      │
      ▼  reports L-drift. Above 3 % we say "not converged", we don't fake precision.
```

## 3. Measured validation (not claims — numbers from this repo's runs)

| Case | Expected | Tier B measured | Δ |
|---|---|---|---|
| DC resistance, 10 mm × 0.3 mm × 35 µm Cu, no plane | 16.381 mΩ (ρL/A) | 16.381 mΩ | **0.00 %** |
| MIT example `plane.in`: 5 µm line over plane, 600 MHz | R = 15 Ω (handbook in the file) | 15.13 Ω | **+0.9 %** |
| Microstrip 10 mm / 0.3 mm / 0.2 mm gap, L convergence 60×60 → 80×80 | converging | 1.647 → 1.642 nH | **−1.7 % (stable)** |
| Fixture `VIN` 15 mm straight trace, loop L @ 50 MHz | 4.045 nH (Tier A microstrip) | 4.354 nH | **+7.7 %** |
| Fixture `VIN` convergence 25×10 → 60×60 cells | — | 4.396 → 4.354 nH | **−0.1 % (converged)** |

The VIN case is the apples-to-apples one: a straight trace, so the closed form and the field
solver describe the same physical loop. **+7.7 % agreement** is exactly what the literature
predicts for a closed-form microstrip against a finite-plane solve.

The SW case is *not* a bug. It is the point:

```
SW = 20 mm on F.Cu + 15 mm on F.Cu + 15 mm on B.Cu, joined by one via, over a partial In1.Cu plane

Tier A (three separate infinite-plane microstrips + via):   13.16 nH
Tier B (the actual loop through a finite plane):            19.29 nH   (+46.6 %)
```

The return current has to travel ~36 mm through In1.Cu and cross layers through a single 1.6 mm
barrel. Tier A never sees that. **19.29 nH is what the copper does.**

Both numbers appear in the report and the UI, side by side, with the Δ and the convergence drift.
Injection uses Tier B.

## 4. Installing the solver

**Docker (recommended)** — the `worker/Dockerfile` compiles FastHenry in a builder stage, so
`docker compose build` needs nothing from you.

**Local** — one command, with a self-verifying smoke test:

```bash
./scripts/build-fasthenry.sh
# ==> installed worker/vendor/fasthenry/bin/fasthenry
# ==> smoke test: R_dc = 0.016381 Ω (expected 0.016381 Ω)
# ==> smoke test PASSED
```

It clones [ediloren/FastHenry2](https://github.com/ediloren/FastHenry2) (the MIT/FastFieldSolvers
64-bit port), applies modern-GCC build flags (`-O2 -std=gnu89 -fcommon` plus a handful of
suppressions — this is 1996 K&R C), and verifies the binary against an analytic DC resistance
before installing.

Then point the worker at it — `FH_BIN` is optional if you used the default path:

```bash
FH_BIN=$PWD/worker/vendor/fasthenry/fasthenry \
  python3 -m uvicorn main:app --app-dir worker --host 0.0.0.0 --port 8000
```

**No solver? It degrades honestly.** `/health` reports `tier_b_available: false`, the UI shows a
banner explaining why, the report header says "Tier A — closed-form (no field solver available)",
and `meta.json` records the fallback. Nothing is silently upgraded.

## 5. Traps found the hard way (so you don't re-live them)

| Symptom | Root cause | Fix |
|---|---|---|
| R was exactly **1000×** too high | `.units mm` scales *resistivity* by the length unit. We used the µm-era σ = 58.1; with mm you need σ ≈ 5.814e4 | `SIGMA_CU_MM = (1/ρ_SI) × 1e-3` |
| `don't know what piece this is in seg e30` | `npfar`/`npnear` were emitted **after** the element list. They must be `+` continuation lines of the `g1` block | emit them inside the plane definition |
| `filaments had identical centers` + R = 46 Ω | The via was added twice: once from the explicit list, once inferred from two layers meeting at the same (x, y). Two coincident filaments short the model | vias are **inferred only**, never both |
| Reference gap read 0.2 mm instead of 0.2104 mm | Adjacent-layer indexing bug: the dielectric-search window excluded the single dielectric between neighbouring coppers | index by **stackup position**, not copper index |
| FastHenry crashes / infinite loop | 64-bit pointer truncation in the original MIT 3.0 (`ualloc` had no prototype → implicit `int` return) | use the FastFieldSolvers 64-bit port, not the 1996 tarball |
| Trivial cases hang forever | 1992 FastCap's allocator on 64-bit | not wired; see §6 |

## 6. What is *not* solved (yet)

- **Capacitance** is still Tier A closed-form. FastCap (1992) builds but hangs on trivial inputs
  (K&R allocator bugs on 64-bit); FasterCap 6.0.7's Linux binary needs wxWidgets 3.0, which isn't
  packaged on Debian trixie, and its source is GPL — which is a licensing decision, not just a
  build one (see `NOTICE.md` §3). Tracked as **T-304**.
- **Mutual inductance between different nets** — FastHenry can do it (multiple ports give a full
  Z-matrix, and `MakeLcircuit` emits K statements), but the pipeline still solves one net per port.
  Tracked as **T-303b**.
- **Frequency sweeps** — the module solves a single f₀ per net today. `.freq fmin=… fmax=…` accepts
  a range; exposing it as a Foster ladder is **T-306**.
- **Plane voids and splits** — the plane is meshed as a solid rectangle. `hole` syntax exists in
  FastHenry; KiCad zone geometry isn't mapped to it yet (**T-102** follow-up).

## 7. How the numbers reach the report

Every net that gets field-solved carries `tier_b` in `/api/analyze`:

```json
"tier_b": {
  "r_ohm": 0.0591284, "l_h": 1.928706e-08, "f_hz": 5e7,
  "solver": "fasthenry-3.0.1",
  "filaments": 5753, "meshes": 634, "runtime_s": 1.11,
  "convergence": { "points": [...], "l_drift": 0.0151, "converged": true, "tol": 0.03 },
  "geometry": { "ref_layer": "In1.Cu", "gap_mm": 0.2, "n_vias_modelled": 1, ... },
  "delta_vs_tier_a": { "r_pct": -25.9, "l_pct": 46.6 }
}
```

`parasitics.lib` then carries the Tier B R and L with a provenance comment naming the filament
count and the mesh drift. `parasitics-meta.json` records the solver path and version. No number in
a generated file is ever un-attributed.

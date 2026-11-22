# RESEARCH — PCB Parasitics × QSPICE × Professional Web Apps

> Compiled 2026-11-22. Items marked **[verified]** were directly observed in this project; items marked **[source]** come from cited publications/links. Nothing is invented; unknowns are marked `TBD`.

---

## 1. Executive summary

The tool extracts parasitic **R (incl. skin/proximity effects), partial self/mutual L, and C** from PCB copper geometry and dielectric, turns them into a SPICE subcircuit, and injects them into a QSPICE project. Two independent research tracks converge on the same architecture:

- **PEEC** (Partial Element Equivalent Circuit) — Ruehli 1974; the physics inside Ansys Q3D; gives R/L/M and, with dielectrics, capacitances (Ruehli 1973; Ruehli & Heeb 1992).
- **Open-source field solvers** — MIT's FastHenry2 (R/L/M) and FasterCap/FastCap2 (C), ported/maintained by FastFieldSolvers (Enrico Di Lorenzo); used and *validated against measurement* in TU Ilmenau's PCIM work and the PCBParC project.

QSPICE projects are files we can parse and augment (§4). A professional web app around this pipeline is feasible today with ~6–9 months of focused effort (see `plan.md`).

---

## 2. The physics & closed-form kernel (Tier A)

**Skin depth** — δ = √(2ρ / (ω·μ₀μᵣ)); copper at 1 MHz ≈ 66 µm, at 100 MHz ≈ 6.6 µm. Rule of thumb for meshing: filament width ≤ δ (FastHenry guideline). [source]

**DC + AC resistance** — R_dc = ρ·l/(w·t); above δ, current crowds to the surface; use Wheeler/Fringing-aware formulas or an AC ratio R_ac/R_dc ≈ (t/2δ) for t ≫ δ (approx). Proximity effect: add Dowell-type factor for adjacent conductors; mandatory for parallel power-loop traces (errors >2× if ignored). [source]

**Loop inductance (power electronics focus)** — L_loop ≈ 2·μ₀·l·(geometry factor); the commutation loop (e.g., half-bridge) dominates overshoot: V = L·di/dt with di/dt up to kA/µs. Grover (1946, *Inductance Calculations*) gives rectangular-filament formulas used industry-wide; Rosa (1908) for round conductors. Paul (*Inductance: Loop and Partial*, Wiley 2010) is the modern rigorous reference. [source]

**Partial inductance (general)** — For rectangular filaments: self L_p = 2·μ₀·l/(2π)·[ln(2l/w+t) + 0.5 + …] (Grover); mutual M between filaments with distance d ≫ l: M ≈ 2·L_p·(l/d)²·cosθ (watch sign & validity); general case via Maxwell's formula numerically integrated. Closed forms break down when filaments nearly touch — then only the solver (Tier B) is trustworthy. [source]

**Microstrip (surface)** — IPC-2141A simplified: **Z₀ = (87/√(ε_r+1.41)) · ln(5.98·h / (0.8·w + t))**, valid 0.1 < w/h < 3, 1 < εr < 15, ±5–7 %. Hammerstad–Jensen equations are the accurate form (±2 %): ε_eff = ½(ε_r+1) + ½(ε_r−1)·(1+12h/w)^(−½) (surface), Z₀ = (60/√ε_eff)·ln(f(w/h,t)) … exact expression in Gupta/Garg/Bahl (*Microstrip Lines and Slotlines*, Artech House) — implement both, expose "accuracy mode". [source]

**Stripline (symmetric)** — **Z₀ = (60/√ε_r) · ln(4·b / (0.67·π·(0.8·w + t)))**, b = plane spacing; ±1–2 % typical. Embedded microstrip and asymmetric stripline variants per IPC-2141A/Hammerstad. [source]

**Per-unit-length L, C & delay** — Z₀ = √(L′/C′); ε_eff sets v; delay = √(ε_eff)/c (ps/in); C′ and L′ follow from Z₀ and v. Coupled pairs: edge-coupled microstrip/stripline Z_diff ≈ 2Z₀(1 − 0.48·e^(−0.96·s/h)) (approximation; better via field solver). [source]

**Plane/PDN** — spreading inductance & resistance under vias (Grover/Keeth); anti-plane capacitance = ε₀ε_r·A/d; plane resonance f₀ = c/(2·L·√ε_eff). Full-wave needed if wavelength < plane dimensions (GHz). [source]

**Characteristic sign conventions** — Partial L of each conductor is positive; mutual sign follows current reference direction; QSPICE mutual coupling: `K1 Lx Ly k` with 0 ≤ k < 1 (verify |k|<1 after extraction; flag otherwise).

**Passivity** — Extracted matrices R(ω), L(ω) must yield positive-real impedance. PEEC with real resistances & positive L is passive by construction at each frequency point; curve-fitted frequency-dependent R ladders must be validated (Foster sections or eigenvalue audit). See Gustavsen & Semlyen, *IEEE Trans. Power Delivery*, 1999 (vector fitting). [source]

**Validity cheat-sheet (guard rails to encode)**

| Formula | Range | Fails when |
|---|---|---|
| IPC-2141 microstrip | 0.1 < w/h < 3; εr 1–15 | narrow w/h, thick copper, εr(f) dispersion ignored |
| Stripline | symmetric b, buried t | asymmetry > 15 % (then use asym formulas or solver) |
| Grover partial L | filament ≫ width, d not « w,t | adjacent touching filaments → Tier B |
| Skin δ | f ≥ ~10 kHz Cu | below ~1 kHz use DC; ε_r dispersion above ~10 GHz (FR-4) |
| quasi-static PEEC | dimensions « λ | > ~5 GHz or dense via fields → Tier C (openEMS) |

---

## 3. Open-source tools inventory (GitHub & ecosystem)

### Field solvers / extractors
| Tool | Role | License / notes | Link |
|---|---|---|---|
| **FastHenry2** | 3-D magneto-quasi-static R, L(f), partial & mutual, planes | open source (MIT-style; per F-Si wiki, "golden reference"); Windows binaries + source | github.com/ediloren/FastHenry2 |
| **FasterCap** | 3-D/2-D capacitance, inhomogeneous dielectrics, auto-refinement | open source (FastFieldSolvers) | github.com/ediloren/FasterCap |
| **FastCap2** | 3-D capacitance (classic) | open source; predecessor of FasterCap | github.com/ediloren/FastCap2 |
| **FastImp** | Wide-band full-wave impedance | open source | github.com/ediloren/FastImp |
| **VoxHenry** | Voxel-based MQS inductance (complex 3-D) | open source | github.com/acyucel/VoxHenry |
| **ElectroMagnetic Workbench** | GUI (FreeCAD) front-end for FastHenry2 | open source | github.com/ediloren/EM-Workbench-for-FreeCAD |
| **openEMS** | FDTD full-wave solver, Python/Octave, dispersive media, MPI | GPL-3 — use as subprocess, never linked | github.com/thliebig/openEMS · docs.openems.de |
| **Meep** (MIT) | FDTD (photonics-oriented) | GPL | github.com/nano-md/meep — not preferred for PCB conductors |
| **PyFEMM** | Magneto-statics FEA (David Meeker) | open source | useful cross-check for planar loops |

FastFieldSolvers hub: downloads, publications, docs — https://www.fastfieldsolvers.com [source]

### EDA file parsing
| Task | Library | Notes | Link |
|---|---|---|---|
| KiCad board parse | **kiutils** (Py ≥3.10, dataclasses, KiCad 6+) | tracks/vias/zones/pads/stackup; SCM-friendly | github.com/mvnmgrx/kiutils · PyPI `kiutils` |
| KiCad board parse (alt) | **realthunder/kicad_parser** | KiCad 5/6-era s-expr | github.com/realthunder/kicad_parser |
| KiCad API | **pcbnew** Python module | in-KiCad scripting; needs KiCad installed | docs.kicad.org/10.0/en/pcbnew |
| Gerber/Excellon parse | **gerbonara** | RS-274X, Excellon, IPC-356 testpoints; LayerStack auto-detect | github.com/jaseg/gerbonara · PyPI |
| IPC-2581 | stdlib XML (`lxml`) | stackup + geometry in one file; fab-exported | IPC-2581 spec (paid), but files parse freely |
| Nets from schematic↔PCB | KiCad `.net` netlist | designator & net matching | kicad-cli / KiCad export |

### Simulation & verification
| Tool | Role | Notes |
|---|---|---|
| **ngspice** | BSD-licensed SPICE; CI verification proxy | runs anywhere, no Windows needed |
| **PySpice** | Python SPICE netlist builder/runner | glue for automated tests | 
| **QSPICE** | target simulator | Windows-only; free from Qorvo (getqspice.com); **do not bundle** |

### Reference calculators (validation cross-checks, not dependencies)
Saturn PCB Toolkit (freeware), Broadcom AppCAD, Si9000-equivalents; commercial: Ansys Q3D, Cadence Clarity/Sigrity PowerDC, Siemens HyperLynx, Keysight ADS/Momentum, Simbeor — use public benchmarks from their papers to cross-validate Tier B.

---

## 4. QSPICE internals — **verified today against a real `.qsch` file**

### 4.1 File types [source: Qorvo forum, Qorvo docs-linked guides]
`.qsch` schematic · `.qsym` symbol · `.cir` SPICE netlist (ASCII) · `.qraw` waveform data · `.pfg` plot config · `.v` Verilog-A-ish · `.cpp` C++ source block · `.lib`/`.sub` model libraries (LTspice convention)

### 4.2 `.qsch` binary-ish text format (verified)
Downloaded `noise.qsch` from a public example repo and hexdumped it **[verified]**:

```
FF D8 FF DB                     ← 4-byte magic (not JPEG despite sniffing as one)
  AB  schem e m a t i c \n       ← root record, no terminator
  AB  component (1200,1000) 0 0
      AB  symbol V
      AB  type: V BB            ← records: AB … payload … BB (BB optional on some lines)
      AB  line (0,-130) (0,-200) 0 0 0x1000000 -1 -1 BB
      AB  pin (0,200) (0,0) 1 0 0 0x0 -1 "+" BB
      AB BB                     ← BB alone on an indented line = close inner block
  AB BB                         ← close outer block
  AB net (1200,800) 1 13 0 "GND" BB
  AB wire (-6700,-1200) (-6700,-1000) "IN" BB
  AB junction (x,y) … BB
  AB library file: |.model 2N3904 NPN(...) BB   ← embedded SPICE directives, escaped
```

Grammar findings:
- Payload is **single-byte text** (ASCII + `µ` etc. as raw high bytes) with `0xAB` = record start, `0xBB` = record end / block close. Hierarchical indent (2 spaces per level).
- Records seen: `schematic`, `component`, `symbol`, `type`, `description`, `shorted pins`, drawing primitives (`line|rect|zigzag|ellipse|triangle|text`), `pin`, `wire`, `junction`, `net`, `library file: |…`.
- Net topology lives in `wire`/`net`/`junction` records with coordinates and net names — exactly what an additive editor needs.
- **Coordinates** are integer internal units (grid 100 units = small square; component pins at ±200). Unit mapping to mils/mm to be pinned down empirically during implementation (not blocking — we only *add* fresh blocks at fresh coordinates).
- `.cir` export from `.qsch`: QSPICE GUI → View → Netlist; or command mode `QUX -Netlist "file.qsch"` **[source: Qorvo forum #15924]**. `.cir` is not auto-saved; `.qraw` is the waveform output; QSPICE runs batch as `QSPICE64.exe file.cir` (copy binary as `qspice` and `QUX` as `qplot` on PATH per openicdesign/Qspice_CMOSedu **[source]**).
- **QSPICE is Windows-only; freeware from Qorvo; license does not allow redistribution** → server-side simulation uses **ngspice** as the automatic proxy; QSPICE verification is a documented user-side or Windows-runner step. [source]
- There is at least one community MCP server (`kh6570/HAbedini-qspice-mcp`) that inspects/edits `.qsch` programmatically — existence proof that `.qsch` can be machine-edited **[source]**; our additive writer will be independent, minimal, and snapshot-tested.

### 4.3 Injection strategies (decision §plan.md Decision log)
| Mode | What | Robustness | User value |
|---|---|---|---|
| **A. `.cir` rewrite** | Parse netlist → split target nets → insert `R/L/C` + `K` + `.include parasitics.lib` | Highest (text grammar, well-understood SPICE) | Guaranteed correct semantics; diff review |
| **B. Additive `.qsch`** | Append labeled "PCB Parasitics" block (components + wires + net labels + `parasitics.lib` include) on the same sheet or new sheet; **zero existing bytes modified** | High (magic+grammar verified); risk = unknown record variants | Visual, transparent in schematic |
| C. Full `.qsch` rewire | Split existing wires in-place | Medium–Low; layout collisions | Best UX, deferred post-MVP |

**v1.0 ships A (default) + B (opt-in).** Every download includes a unified diff + `manifest.json`.

### 4.4 `parasitics.lib` design (to be refined in T-403)
```
* PCB parasitic network — auto-generated 2026-11-… 
* solver=FastHenry2 mesh=… f0=…MHz source=/uploads/…
.subckt PAR_NET_SW nodes=(SW_a SW_b)
R_PAR_SW_1 SW_a P1 12.4m
L_PAR_SW_1 P1 SW_b 3.9n
C_PAR_SW_1 SW_b 0 850f
.ends PAR_NET_SW
.param PAR_K_SW_GATE=0.62
```
Naming `X_PAR_*`/`R_PAR_*` avoids user namespace collisions; values carry SI units with `.param` where useful; comments carry full provenance.

---

## 5. Papers & authoritative references (numbered)

1. **PAP-01** — A. E. Ruehli, *"Equivalent Circuit Models for Three-Dimensional Multiconductor Systems,"* IEEE T-MTT, vol. 22, no. 3, pp. 216–221, Mar 1974. DOI 10.1109/TMTT.1974.1128201 (also listed as 10.1109/22.310584). **PEEC foundations.**
2. **PAP-02** — A. E. Ruehli, *"Efficient Capacitance Calculations for Three-Dimensional Multiconductor Systems,"* IEEE T-MTT, vol. 21, no. 2, pp. 76–82, Feb 1973.
3. **PAP-03** — A. E. Ruehli & H. Heeb, *"Circuit models for three-dimensional geometries including dielectrics,"* IEEE T-MTT, vol. 40, no. 7, pp. 1507–1516, July 1992. DOI 10.1109/22.146370.
4. **PAP-04** — K. Kamon, M. Tsuk, J. K. White, *"Fasthenry: A multipole accelerated 3-D inductance extraction program,"* IEEE T-MTT, vol. 42, no. 9, pp. 1750–1758, Sept 1994. (Software: ediloren/FastHenry2)
5. **PAP-05** — K. S. Nabors & J. K. White, *"Fastcap: A multipole accelerated 3-D capacitance extraction program,"* IEEE T-MTT, vol. 39, no. 9, pp. 1498–1506, Sept 1991.
6. **PAP-06** — G. Gustavsen & A. Semlyen, *"Rational approximation of frequency responses of dielectric losses in cables by vector fitting,"* IEEE T-PWRD, vol. 14, no. 3, pp. 1052–1061, 1999. **Vector fitting / passivity.**
7. **PAP-07** — S. S. Hammerstad & Ø. Jensen, *"Accurate models for microstrip computer-aided design,"* IEEE MTT-S Int. Microwave Symp. Digest, pp. 407–409, 1980.
8. **PAP-08** — F. W. Grover, *Inductance Calculations: Working Formulas and Tables*, Dover, 1946.
9. **PAP-09** — J. R. Brauer, *Magnetic Actuators and Sensors* (2nd ed.), or R. Paul, *Inductance: Loop and Partial*, Wiley, 2010. **Loop/partial L.**
10. **PAP-10** — H. W. Johnson & M. Graham, *High-Speed Digital Design: A Handbook of Black Magic*, Prentice Hall, 1993.
11. **PAP-11** — E. Bogatin, *Signal and Power Integrity — Simplified* (3rd ed.), Prentice Hall/Pearson, 2018.
12. **PAP-12** — IPC-2141A, *Design Guide for High-Speed Controlled Impedance Circuit Boards*, IPC, 2004 (+errata).
13. **PAP-13** — IPC-2221B, *Generic Standard on Printed Board Design*; IPC-2152 (current capacity); IPC-2581 (fabrication data); IPC-D-356A (netlist/test points).
14. **PAP-14** — *"Automated PCB Parasitics Extraction from EDA Tools for Power Electronics Design Support"*, IEEE Xplore doc #9472438 (VDE/PCIM 2021-era); TU Ilmenau. Algorithm: EDA parser → FastHenry2 + FasterCap; accuracy verified against experiment. Related symposium slides: Omicron Lab, "Power Analysis & Design Symposium 2022" — https://www.omicron-lab.com/fileadmin/assets/Training_and_Events/Power_Analysis_and_Design-Symposium/2022/Presentation_TU-Ilmenau.pdf
15. **PAP-15** — *"Accurately modelling of parasitics in power electronics circuits using an easy RLC-extraction method"*, ResearchGate #254042181; tool developed: **PCBParC** (Matlab, FastHenry/FastCap backend); compared vs CST & measurement; "predicts rise times, overshoots, oscillation behaviors very well."
16. **PAP-16** — A. Antonini, *"PEEC capacitance extraction of 3-D interconnects,"* IET Sci. Meas. Technol., vol. 1, no. 4, 2007 (+ Antonini's many PEEC reviews). Overview hub: Clemson CECAS — https://cecas.clemson.edu/cvel/modeling/tutorials/techniques/peec/peec.html
17. **PAP-17** — T. Spice / community docs — QSPICE file extensions & CLI; Qorvo forum threads [#14296 extensions](https://forum.qorvo.com/t/file-extensions-used-by-qspice/14296), [#15924 netlist location](https://forum.qorvo.com/t/where-can-i-find-the-netlist-and-logfile/15924), [#21240 .meas/QPOST](https://forum.qorvo.com/t/how-do-i-generate-an-output-file-for-meas/21240)
18. **PAP-18** — openEMS: T. Thiele et al., openEMS project — https://www.openems.de · github.com/thliebig/openEMS-Project ; docs.openems.de (Python FDTD, dispersive materials, MPI, NF2FF).
19. **PAP-19** — CMOSedu Qspice repo — filetype/CLI documentation — github.com/openicdesign/Qspice_CMOSedu
20. **PAP-20** — QSpice examples corpus (for snapshot testing `.qsch`) — github.com/QSpice-Circuits/Qspice-examples ; github.com/KSKelvin-Github/Qspice

**Reading order:** PAP-01 → PAP-10/11 (intuition) → PAP-14/15 (PCB-specific pipeline, closest to our product) → PAP-04/05 (solvers we ship) → PAP-07/12/08 (Tier A formulas) → PAP-06 (passivity, if doing frequency-dependent R).

---

## 6. Strategy landscape & positioning

| Competitor | What it does | Gap we fill |
|---|---|---|
| Ansys Q3D Extractor | PEEC/FEM parasitic matrices → SPICE/IBIS | $$$, closed, no QSPICE rewriting, needs expert |
| Cadence Clarity / Sigrity PowerDC | Full-wave SI/PI | same |
| Siemens HyperLynx / Simcenter | SI/pi + 3D | same |
| Keysight ADS/Momentum | MoM 2.5D/3D | microwave-centric |
| Simbeor | SI/PI on layouts | closed |
| Free: Saturn PCB Toolkit, AppCAD | calculators | single-trace only, no project injection |
| Free: FastHenry/FasterCap raw | extraction | **no pipeline, no QSPICE, no report** — exactly our layer |
| Free: openEMS | full-wave | same |

**Positioning:** "Q3D-class parasitic injection, open-sourced, QSPICE-native, one upload."

---

## 7. Validation plan (accuracy you can defend)

**Golden geometries (unit tests, CI):**
1. 50 Ω microstrip (FR-4 εr 4.3, h=0.2 mm): C′, L′, Z₀ vs closed form ±2 %.
2. Square air loop 20×20 mm wire 1 mm: L vs Grover ±3 %.
3. Via barrel: L vs published formula ±5 %.
4. Adjacent parallel traces: K mutual vs AppCAD/Saturn ±5 %.
5. Capacitance of 3-plate stack-up: FasterCap vs analytic ±1 %.

**Published benchmarks (integration tests, tolerance 5–15 %):**
- TU Ilmenau power-loop extractions (PAP-14) — replicate published R/L trends.
- PCBParC MOSFET half-bridge case (PAP-15) — overshoot trend vs reported.

**Numerical hygiene:**
- Mesh refinement until ΔZ(f) < 1 % between refinement steps (FastHenry `-aoff` off; FasterCap auto-refine).
- Skin-depth filament rule enforced automatically; warn if violated.
- Passivity audit on every result (PAP-06 method for fitted ladders).
- Report includes uncertainty: closed-form ±X %, solver ±Y % (from refinement study), never "exact".

**Comparison rig (optional, aspirational):** user-runnable script exports same geometry to Q3D/SIwave/Clarity if licensed; diff table in docs — turns accuracy into a community contribution.

---

## 8. Security & compliance notes (parasitic-domain specifics)

- Uploaded files = user IP. TTL-delete artifacts (default 24 h), signed URLs, per-object ACLs, no cross-user listing, no analytics on content.
- Solver subprocesses: no network, rlimits, timeout, clean env, read-only input mount.
- ZIP: max 100 MB / 10k files / ratio cap; path sanitization; `.exe/.dll/.so` in uploads treated as data, never executed (QSPICE models for `.cpp` injection are passed through as text only).
- Marks: "QSPICE" is a trademark of Qorvo — nominative use only ("for QSPICE®"), no implied endorsement.
- GPL hygiene: solvers invoked as subprocesses; no GPL code is linked into our codebase; FastHenry2/FasterCap are permissive-ish but we keep the boundary clean regardless.

---

## 9. Source list (URLs used)

- https://en.wikipedia.org/wiki/Parasitic_extraction
- https://wiki.f-si.org/index.php/Open_Source_Parasitic_Extraction
- https://www.fastfieldsolvers.com (software, docs, publications)
- https://github.com/ediloren/FastHenry2 · …/FasterCap · …/FastCap2 · …/FastImp · …/EM-Workbench-for-FreeCAD · https://github.com/acyucel/VoxHenry
- https://www.openems.de · https://github.com/thliebig/openEMS · https://github.com/thliebig/openEMS-Project · https://docs.openems.de
- https://www.epsilonforge.com/post/open-source-electromagnetics/ (open-source CEM survey, 2025)
- https://ieeexplore.ieee.org/document/9472438 (TU Ilmenau paper)
- https://www.omicron-lab.com/fileadmin/assets/Training_and_Events/Power_Analysis_and_Design-Symposium/2022/Presentation_TU-Ilmenau.pdf
- https://www.researchgate.net/publication/254042181_Accurately_modelling_of_parasitics_in_power_electronics_circuits_using_an_easy_RLC-extraction_method
- https://cecas.clemson.edu/cvel/modeling/tutorials/techniques/peec/peec.html
- https://www.ipc2141 articles: pcbsync.com/ipc-2141 · flux.ai/p/tools/pcb-impedance-calculator (formula context)
- https://github.com/jaseg/gerbonara
- https://mvnmgrx/kiutils (github.com/mvnmgrx/kiutils) · docs.kicad.org/10.0/en/pcbnew (pcbnew API) · github.com/realthunder/kicad_parser
- https://forum.qorvo.com/t/file-extensions-used-by-qspice/14296 · https://forum.qorvo.com/t/where-can-i-find-the-netlist-and-logfile/15924 · https://forum.qorvo.com/t/how-do-i-generate-an-output-file-for-meas/21240 · https://forum.qorvo.com/t/qspice-a-new-simulator-for-electronic-circuits-part-1/ (extensions overview; powerelectronicsnews.com mirror)
- https://github.com/openicdesign/Qspice_CMOSedu (CLI usage)
- https://github.com/QSpice-Circuits/Qspice-examples · https://github.com/KSKelvin-Github/Qspice (format specimens)
- https://github.com/kh6570/HAbedini-qspice-mcp (programmatic `.qsch` handling exists)
- QSPICE download: https://www.qorvo.com/design-hub/design-tools/interactive/qspice · https://getqspice.com/InstallQSPICE.exe

## 10. Unknowns & measurement tasks (assigned as T-tasks)

- `.qsch` internal unit ↔ mm/mil mapping — measure on known-grid file (T-402)
- `.qsch` versioning/magic variants across QSPICE releases — corpus scan of ≥30 files (T-402)
- QSPICE `K` mutual syntax edge cases (max couplings, sign handling) — empirical (T-401)
- ngspice vs QSPICE numerical parity on RLC + K — tolerance study (T-406)
- KiCad stackup εr availability for all fab presets — gap analysis (T-204/T-206)

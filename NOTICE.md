# NOTICE — third-party components, licenses & trademarks

This product is an open-core project (decision OQ-06): the engine and web app are MIT (see LICENSE). Hosted/managed offerings are governed by separate commercial terms (to be published before v1.0).

Nothing in this repository is bundled FROM any of the following unless stated; they are referenced as design/validation context or invoked as external tools. Exact license text and pinned versions are recorded at dependency-lock time (task T-010 / T-203 / T-303). Where unsure, we say so rather than assert.

## Solvers & engines (external tools, invoked as subprocesses)

| Component | License (verified) | Notes |
|---|---|---|
| **FastHenry 3.0.1** (`ediloren/FastHenry2`, `master`) | **MIT-style** — "License to use, copy, modify, sell and/or distribute this software and its documentation for any purpose is hereby granted without royalty" (Copyright 2003, MIT Board of Trustees; original 1996 Kamon/Smithhisler/White) | **Built from source, not redistributed.** `scripts/build-fasthenry.sh` and `worker/Dockerfile` compile it at install/build time. The binary has no copyright notice embedded, which is why the source is in the build stage rather than git. Full build instructions in `docs/TIER-B.md` §4 |
| FastCap 2.0 (1992, MIT) | MIT-style (same terms) | **Not used.** Builds on modern GCC with patches but hangs on trivial geometries (K&R allocator bug on 64-bit). T-304 |
| FasterCap 6.0.7 (FastFieldSolvers) | **LGPL-2.1** for the bundled `licence_third_party`, plus **GPL** components; the standalone binary also links wxWidgets (wxWindows Licence) | **Not used, deliberately.** GPL in a hosted proprietary service needs a licensing decision before bundling — that is a product call, not a build fix. Capacitance stays closed-form until T-304 resolves it |
| openEMS (github.com/thliebig/openEMS) | GPL-3.0 | Subprocess isolation, never linked; Tier C (post-MVP) |
| ngspice | BSD-style | Verification proxy; runs in CI |
| PySpice | check upstream (GPL-3 as of recent releases) | Used for test-bench automation only if compatible |

## Parsers & EDA

| Component | Expected license | Notes |
|---|---|---|
| kiutils (mvnmgrx/kiutils) | check upstream at pin time | KiCad 6+ `.kicad_pcb` parser |
| realthunder/kicad_parser | check upstream | Legacy s-expr parser |
| gerbonara (jaseg/gerbonara) | check upstream | Gerber/Excellon RS-274X parsing |
| KiCad pcbnew API | GPL-2.0+ (KiCad) | Used only inside a KiCad runtime when available; not linked into production path |

## Standards & documentation (NOT redistributed)

IPC-2141A, IPC-2221B, IPC-2152, IPC-2581, IPC-D-356A — IPC standards are paid documents; we implement *equations and formats*, we do not include standard text. IPC-2581 files exported by fabs are parsed as data.

## Trademarks

- **QSPICE®** is a trademark of Qorvo, Inc. This project is not affiliated with, endorsed by, or sponsored by Qorvo. "for QSPICE" is used nominatively to describe compatibility.
- **KiCad** is a trademark of its respective owners. **Ansys Q3D**, **Cadence**, **Siemens**, **Keysight**, **Simbeor**, **CST** are trademarks of their respective owners; mentioned only for positioning/comparison.

## User data

Uploaded user designs remain the user's property; artifacts are TTL-deleted (see README / plan Phase 5). No user design is used for training.

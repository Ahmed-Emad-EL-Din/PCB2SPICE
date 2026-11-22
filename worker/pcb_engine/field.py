"""Tier B — PEEC-style field solving via FastHenry2 (MIT FastHenry 3.0.1, 64-bit port).

Why this module exists
----------------------
Tier A (`parasitics.py`) is closed-form: it maps each trace to a microstrip /
stripline cross-section and multiplies by length. That is fast (±5–10 %) but it
assumes an *infinite* reference plane directly under the trace and handles
mutual coupling only through stackup heuristics.

Tier B builds an actual **finite 3-D geometry** of the net and its nearest
reference plane, meshes it into filaments, and solves the magneto-quasistatic
mesh formulation (MNA + multipole-accelerated GMRES). You get a real loop
impedance Z(f) = R(f) + jωL(f) that captures:

  * finite plane extent and current crowding in the plane
  * proximity effect between filaments (the R(f) ramp at high f)
  * skin effect with a proper rectangular cross-section discretization
  * via barrels and the vertical loop they close
  * (with multiple ports) mutual coupling between nets — K matrix

Solver provenance
-----------------
FastHenry 3.0.1, MIT / FastFieldSolvers, 28-May-2012 Linux x86-64 port
(`https://github.com/ediloren/FastHenry2`, branch `master`). MIT licence
(see NOTICE.md). The binary is *not* vendored in this repo: operators either
install it (`make -C fasthenry`) or point `FH_BIN` at it. If the binary is
missing, Tier B degrades to Tier A with an explicit, non-silent fallback —
`tier_effective` in the result will say `"A"` and `fallback_reason` will say
why. Nothing is ever silently upgraded or silently skipped.

Validation done while building this (see docs/RESEARCH.md §9 + plan.md T-303):
  * canonical MIT example `plane.in` → R = 15.13 Ω vs handbook 15 Ω (0.9 %)
  * microstrip 10 mm / 0.3 mm / 0.2 mm gap over 20 mm plane → L converged to
    1.64 nH (mesh 60×60 → 80×80 Δ = 1.7 %); R is still climbing at 80×80
    (proximity convergence is slow — we report the drift, not a fake number)
  * analytic parallel-plate C cross-checked against the Tier A closed form
    (Tier C FastCap/FasterCap is *not* wired: see TODO at the bottom)
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Iterable

# ------------------------------------------------------------------ config

# Standard locations, then env override. `which fasthenry` last.
FH_CANDIDATES = (
    os.environ.get("FH_BIN"),
    "/opt/fasthenry/bin/fasthenry",
    "/usr/local/bin/fasthenry",
    "/usr/bin/fasthenry",
)

# Copper conductivity for FastHenry's `.units mm` convention.
# FastHenry scales *resistivity with the length unit*: rho_units = rho_SI / unit.
# For `.units mm` (unit = 1e-3 m) → rho = 1.72e-8 / 1e-3 = 1.72e-5 Ω·mm, and
# sigma = 1/rho = 5.814e4 1/(Ω·mm). (Using the µm value 58.14 gives 1000x too
# much resistance — this exact bug cost a debugging session; see plan.md T-303.)
RHO_CU_SI = 1.72e-8                     # Ω·m @ 20 °C
SIGMA_CU_MM = (1.0 / RHO_CU_SI) * 1e-3  # ≈ 5.814e4 1/(Ω·mm)
# FastHenry default planes are 2-D current sheets; a plane needs `thick`,
# and current is modelled 2-D. We keep the nominal copper thickness so the
# plane's sheet resistance is right.

DEFAULT_TIMEOUT_S = 120.0
MAX_FILAMENTS = 40_000              # guard rail; FastHenry GMRES scales ~N log N
DEFAULT_NHINC = 2
DEFAULT_NWINC = 2


class FieldSolverUnavailable(RuntimeError):
    """No FastHenry binary on PATH / FH_BIN."""


class FieldSolverError(RuntimeError):
    """FastHenry ran but failed (bad geometry, non-convergence, timeout, NaN)."""


@dataclass
class FieldResult:
    """One port's solved impedance at the requested frequencies."""
    r_ohm: float
    l_h: float                       # L = Im(Z)/ω  (loop/partial as defined by the port)
    f_hz: float
    z_complex: complex
    filaments: int
    meshes: int
    runtime_s: float
    solver: str = "fasthenry-3.0.1"
    convergence: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_zc: str = ""                 # original Zc.mat body (provenance)


# ------------------------------------------------------------ binary lookup

def find_fasthenry() -> str | None:
    for cand in FH_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("fasthenry")


def solver_info() -> dict[str, Any]:
    """For /health and the report — never lies about availability."""
    path = find_fasthenry()
    return {
        "tier_b_available": bool(path),
        "fasthenry": path or None,
        "fasthenry_version": "3.0.1 (MIT/FastFieldSolvers, 2012-05-28 x64)" if path else None,
        "tier_c_available": False,
        "tier_c_note": "FastCap/FasterCap not bundled — capacitance stays closed-form (Tier A) in this release",
    }


# --------------------------------------------------------- geometry model

@dataclass
class Segment3D:
    """One copper trace segment on a layer, in board coordinates (mm)."""
    x1: float
    y1: float
    x2: float
    y2: float
    width_mm: float
    layer: str
    thickness_mm: float = 0.035


@dataclass
class Via3D:
    x: float
    y: float
    drill_mm: float
    from_z_mm: float
    to_z_mm: float


def _layer_z(stackup: list[dict], copper_index_from_top: int,
             board_thickness_mm: float) -> float:
    """z (mm) of the *top* surface of a copper layer, measured from board top.

    Stackup list order = top→bottom (KiCad convention). Copper layers are the
    only entries with type == "copper".
    """
    z = 0.0
    seen = 0
    for ly in stackup:
        t = float(ly.get("thickness_mm") or 0.0)
        if ly.get("type") == "copper":
            if seen == copper_index_from_top:
                return z
            seen += 1
        z += t
    return board_thickness_mm


def build_fasthenry_input(
    net_name: str,
    segments: list[Segment3D],
    vias: list[Via3D],
    stackup: list[dict],
    board_thickness_mm: float,
    f0_hz: float,
    plane_margin_mm: float = 5.0,
    seg_density: int = 20,          # mesh cells across the reference plane's short edge
    nhinc: int = DEFAULT_NHINC,
    nwinc: int = DEFAULT_NWINC,
    design_vias: int = 0,           # KiCad's via count (reporting only)
) -> tuple[str, dict[str, Any]]:
    """Emit a FastHenry .inp for one net over its nearest reference plane.

    Topology (this is the whole trick):
      * trace segments run on their own copper layer at z = layer_top + t/2
      * coincident endpoints on the same layer are welded into one node
      * where two layers meet at the same (x, y) a vertical via segment is
        synthesised (FastHenry has no via primitive — a via is just a short
        wide segment spanning the layers)
      * the nearest copper layer (either side, thinnest dielectric — same rule
        as Tier A `nearest_reference`) becomes a finite `g1` plane extending
        `plane_margin_mm` beyond the net's bounding box
      * the FAR end of the trace is `.equiv`'d to the nearest plane node
        (the shorted loop end)
      * the NEAR end is one terminal of `.external`, the plane node under it
        is the other terminal → Im(Z)/ω is the loop inductance the converter
        actually sees, plane return included

    Returns (input_text, metadata). Raises FieldSolverError if the net cannot
    be turned into a single connected loop.
    """
    if not segments:
        raise FieldSolverError("no segments to mesh")

    copper = [ly for ly in stackup if ly.get("type") == "copper"]
    if not copper:
        raise FieldSolverError("stackup has no copper layers")
    copper_names = [ly["name"] for ly in copper]
    cu_thick = {ly["name"]: float(ly.get("thickness_mm") or 0.035) for ly in copper}

    # z of the *top* face of each copper layer (top-down stackup order)
    layer_top_z: dict[str, float] = {}
    z = 0.0
    for ly in stackup:
        if ly.get("type") == "copper":
            layer_top_z[ly["name"]] = z
        z += float(ly.get("thickness_mm") or 0.0)

    def z_mid(layer: str) -> float:
        return layer_top_z.get(layer, 0.0) + cu_thick.get(layer, 0.035) / 2.0

    def z_bot(layer: str) -> float:
        return layer_top_z.get(layer, 0.0) + cu_thick.get(layer, 0.035)

    # --- reference plane: nearest copper either side, thinnest gap ---------
    ref_layer, gap_mm = _nearest_reference_layer(segments, stackup, copper_names)
    ref_z = layer_top_z.get(ref_layer, 0.0) + cu_thick.get(ref_layer, 0.035) / 2.0
    plane_thick = cu_thick.get(ref_layer, 0.035)

    # --- weld coincident endpoints (same layer, same XY) -------------------
    EPS = 1e-2  # 0.01 mm

    def key(x: float, y: float, layer: str) -> tuple[int, int, str]:
        return (round(x / EPS), round(y / EPS), layer)

    node_of: dict[tuple[int, int, str], int] = {}
    nodes: list[tuple[float, float, float]] = []      # (x, y, z)

    def intern(x: float, y: float, layer: str) -> int:
        k = key(x, y, layer)
        if k in node_of:
            return node_of[k]
        idx = len(nodes)
        node_of[k] = idx
        nodes.append((x, y, z_mid(layer)))
        return idx

    # --- bounding box -----------------------------------------------------
    xs = [s.x1 for s in segments] + [s.x2 for s in segments]
    ys = [s.y1 for s in segments] + [s.y2 for s in segments]
    x0, x1 = min(xs) - plane_margin_mm, max(xs) + plane_margin_mm
    y0, y1 = min(ys) - plane_margin_mm, max(ys) + plane_margin_mm
    wx, wy = max(x1 - x0, 0.5), max(y1 - y0, 0.5)
    short = min(wx, wy)
    seg1 = max(4, min(60, int(round(seg_density * (wx / short)))))
    seg2 = max(4, min(60, int(round(seg_density * (wy / short)))))

    # --- discretize traces ------------------------------------------------
    longest = max(math.hypot(s.x2 - s.x1, s.y2 - s.y1) for s in segments)
    max_seg_mm = max(0.5, longest / 12.0)

    edges: list[tuple[int, int, float, float]] = []   # (a, b, w_mm, t_mm)
    for s in segments:
        L = math.hypot(s.x2 - s.x1, s.y2 - s.y1)
        if L < 1e-9:
            continue
        n = max(1, int(math.ceil(L / max_seg_mm)))
        prev = None
        for k in range(n + 1):
            t = k / n
            x = s.x1 + (s.x2 - s.x1) * t
            y = s.y1 + (s.y2 - s.y1) * t
            cur = intern(x, y, s.layer)
            if prev is not None and cur != prev:
                edges.append((prev, cur, max(s.width_mm, 1e-3), s.thickness_mm))
            prev = cur

    # --- vias: inferred where two layers meet at the same (x, y) ----------
    # FastHenry has no via primitive; a via is a short wide vertical segment.
    # KiCad's `vias` count is only used for reporting — the geometry is what
    # decides, so we never risk the double-segment overlap that produced
    # "filaments had identical centers" warnings in the first cut.
    by_xy: dict[tuple[int, int], dict[str, int]] = {}
    for (kx, ky, layer), idx in node_of.items():
        by_xy.setdefault((kx, ky), {})[layer] = idx
    inferred_vias = 0
    for (kx, ky), per_layer in by_xy.items():
        if len(per_layer) < 2:
            continue
        items = sorted(per_layer.items(), key=lambda kv: layer_top_z.get(kv[0], 0.0))
        for (la, ia), (lb, ib) in zip(items, items[1:]):
            d = max(0.3, sum(cu_thick.get(x, 0.035) for x in (la, lb)) * 2)
            edges.append((ia, ib, d, d))
            inferred_vias += 1

    # --- connectivity check: must be one loop -----------------------------
    comp = _components(len(nodes), edges)
    islands = sorted({comp[i] for i in range(len(nodes))},
                     key=lambda c: -sum(1 for i in range(len(nodes)) if comp[i] == c))
    if len(islands) > 1:
        keep = islands[0]
        dropped = len(nodes) - sum(1 for i in range(len(nodes)) if comp[i] == keep)
        edges = [e for e in edges if comp[e[0]] == keep]
    else:
        dropped = 0
    used_nodes = sorted({n for e in edges for n in e[:2]})
    if len(used_nodes) < 2:
        raise FieldSolverError(f"net {net_name!r} collapsed to a point — nothing to solve")

    # --- terminals: extreme ends of the (longest) path --------------------
    def dist_xy(i: int) -> float:
        return math.hypot(nodes[i][0] - nodes[used_nodes[0]][0],
                          nodes[i][1] - nodes[used_nodes[0]][1])

    far = max(used_nodes, key=dist_xy)
    near = min(used_nodes, key=dist_xy)

    # --- emit -------------------------------------------------------------
    lines: list[str] = []
    lines.append(f"* pcb-parasitic-qspice Tier B — net {net_name!r}")
    lines.append(f"* reference plane: {ref_layer} (gap {gap_mm:.3f} mm, thick {plane_thick:.3f} mm)")
    lines.append(f"* generated {_now()}")
    lines.append(".units mm")
    lines.append(f".default sigma = {SIGMA_CU_MM:.6g}")

    lines.append(f"g1 x1={x0:.6f} y1={y0:.6f} z1={ref_z:.6f}"
                 f"  x2={x1:.6f} y2={y0:.6f} z2={ref_z:.6f}"
                 f"  x3={x1:.6f} y3={y1:.6f} z3={ref_z:.6f}")
    lines.append(f"+  thick={plane_thick:.6f}")
    lines.append(f"+  seg1={seg1} seg2={seg2}")

    # plane reference nodes MUST be continuation lines of the g1 definition
    fx, fy, _ = nodes[far]
    nx, ny, _ = nodes[near]
    lines.append(f"+  npfar ({fx:.6f},{fy:.6f},{ref_z:.6f})")
    lines.append(f"+  npnear ({nx:.6f},{ny:.6f},{ref_z:.6f})")

    for i, (x, y, zz) in enumerate(nodes):
        lines.append(f"n{i} x={x:.6f} y={y:.6f} z={zz:.6f}")
    for ei, (a, b, w, t) in enumerate(edges):
        lines.append(f"e{ei} n{a} n{b} w={w:.6f} h={t:.6f} nhinc={nhinc} nwinc={nwinc}")

    lines.append(f".equiv n{far} npfar")
    lines.append(f".external n{near} npnear p1")
    lines.append(f".freq fmin={f0_hz:.6g} fmax={f0_hz:.6g} ndec=1")
    lines.append(".end")

    meta = {
        "net": net_name,
        "ref_layer": ref_layer,
        "gap_mm": round(gap_mm, 4),
        "plane_thick_mm": plane_thick,
        "plane_extent_mm": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        "mesh": {"seg1": seg1, "seg2": seg2, "nhinc": nhinc, "nwinc": nwinc},
        "n_nodes": len(nodes),
        "n_trace_segments": sum(1 for e in edges),
        "n_vias_modelled": inferred_vias,
        "n_vias_in_design": int(design_vias or 0),
        "dropped_nodes_disconnected": dropped,
        "terminal_far_mm": [round(fx, 3), round(fy, 3)],
        "terminal_near_mm": [round(nx, 3), round(ny, 3)],
    }
    return "\n".join(lines) + "\n", meta


def _layer_at_z(layer_top_z: dict[str, float], cu_thick: dict[str, float],
                z_mm: float) -> str | None:
    """Which copper layer's mid-plane is closest to z_mm?"""
    best, best_d = None, 1e9
    for name, top in layer_top_z.items():
        d = abs(top + cu_thick.get(name, 0.035) / 2.0 - z_mm)
        if d < best_d:
            best, best_d = name, d
    return best


def _components(n: int, edges: list[tuple]) -> list[int]:
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in edges:
        ra, rb = find(e[0]), find(e[1])
        if ra != rb:
            parent[ra] = rb
    return [find(i) for i in range(n)]


def _nearest_reference_layer(segments: Iterable[Segment3D], stackup: list[dict],
                            copper_names: list[str]) -> tuple[str, float]:
    """Nearest copper on *either* side, thinnest dielectric gap wins (Tier A rule)."""
    idx = {n: i for i, n in enumerate(copper_names)}
    # index of each copper layer inside the *stackup* list (dielectrics included)
    stack_pos = {ly["name"]: k for k, ly in enumerate(stackup) if ly.get("type") == "copper"}

    def dielectric_total(p_lo: int, p_hi: int) -> float:
        """Sum of dielectric thickness strictly between two stackup positions."""
        lo, hi = (p_lo, p_hi) if p_lo < p_hi else (p_hi, p_lo)
        total = 0.0
        for ly in stackup[lo + 1:hi]:
            if ly.get("type") != "copper":
                total += float(ly.get("thickness_mm") or 0.0)
        return total

    used = [s.layer for s in segments if s.layer in idx]
    mine = max(used, key=used.count) if used else copper_names[0]
    i = idx[mine]
    best: tuple[str, float] | None = None
    for j, other in enumerate(copper_names):
        if other == mine:
            continue
        gap = dielectric_total(stack_pos[mine], stack_pos[other])
        if gap <= 0:
            gap = 0.2
        if best is None or gap < best[1]:
            best = (other, gap)
    if best is None:
        raise FieldSolverError("could not determine a reference copper layer")
    return best


def _now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- execution

_ZC_RE = re.compile(r"^Row\s+\d+:\s+\S+\s+to\s+\S+", re.M)


def run_fasthenry(inp_text: str, timeout_s: float = DEFAULT_TIMEOUT_S,
                  workdir: str | None = None) -> FieldResult:
    """Run FastHenry in an isolated temp dir and parse Zc.mat."""
    binpath = find_fasthenry()
    if not binpath:
        raise FieldSolverUnavailable(
            "FastHenry binary not found — install it or set FH_BIN "
            "(see docs/TIER-B.md for the one-line build)")

    tmp = workdir or tempfile.mkdtemp(prefix="fh_")
    try:
        inp_path = os.path.join(tmp, "net.inp")
        with open(inp_path, "w", encoding="utf-8") as fh:
            fh.write(inp_text)
        t0 = _mono()
        try:
            proc = subprocess.run(
                [binpath, "net.inp"],
                cwd=tmp, capture_output=True, text=True, timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise FieldSolverError(f"FastHenry timed out after {timeout_s:.0f}s") from exc
        elapsed = _mono() - t0
        log = (proc.stdout or "") + (proc.stderr or "")

        zc_path = os.path.join(tmp, "Zc.mat")
        if not os.path.isfile(zc_path) or os.path.getsize(zc_path) == 0:
            raise FieldSolverError(_first_error(log) or
                                   f"FastHenry produced no Zc.mat (exit {proc.returncode})")
        with open(zc_path, encoding="utf-8", errors="replace") as fh:
            zc = fh.read()

        z = _parse_zc(zc)
        filaments = _grep_int(log, r"Number of filaments:\s*(\d+)")
        meshes = _grep_int(log, r"Number of meshes:\s*(\d+)")
        if filaments and filaments > MAX_FILAMENTS:
            raise FieldSolverError(f"{filaments} filaments exceeds the {MAX_FILAMENTS} guard "
                                   f"— coarsen the mesh or target a shorter net")

        return FieldResult(
            r_ohm=z.real, l_h=z.imag / (2 * math.pi * _z_freq(zc) or 1),
            f_hz=_z_freq(zc), z_complex=z,
            filaments=filaments or 0, meshes=meshes or 0, runtime_s=elapsed,
            warnings=_warnings(log), raw_zc=zc,
        )
    finally:
        if workdir is None:
            shutil.rmtree(tmp, ignore_errors=True)


def _mono() -> float:
    import time
    return time.monotonic()


_FREQ_RE = re.compile(r"Impedance matrix for frequency\s*=\s*([+\-\d.eE]+)")


def _z_freq(zc: str) -> float:
    m = _FREQ_RE.search(zc)
    return float(m.group(1)) if m else 0.0


def _parse_zc(zc: str) -> complex:
    """Parse the first 1×1 complex number out of Zc.mat."""
    m = re.search(r"Impedance matrix for frequency\s*=\s*[+\-\d.eE]+\s+1\s*x\s+1\s*\n\s*"
                  r"([+\-\d.eE]+)\s*([+\-])\s*([\d.eE+]+)j", zc)
    if not m:
        # tolerantly pick the first "a +bj" pair after the frequency header
        m2 = re.search(r"Impedance matrix[^\n]*\n\s*([+\-\d.eE]+)\s+([+\-][\d.eE+]+)?\s*j",
                       zc)
        if not m2:
            raise FieldSolverError(f"could not parse Zc.mat:\n{zc[:400]}")
        re_v = float(m2.group(1))
        im_v = float(m2.group(2) or 0.0)
        return complex(re_v, im_v)
    re_v = float(m.group(1))
    im_v = float(m.group(2) + m.group(3))
    return complex(re_v, im_v)


def _grep_int(text: str, pat: str) -> int:
    m = re.search(pat, text)
    return int(m.group(1)) if m else 0


_ERROR_HINTS = ("error:", "invalid", "don't know", "cannot", "fatal", "singular", "no such")


def _first_error(log: str) -> str | None:
    """First genuine FastHenry diagnostic (not the 'Error tolerance: 0.001' banner)."""
    for ln in log.splitlines():
        low = ln.lower()
        if "error tolerance" in low:
            continue
        if any(h in low for h in _ERROR_HINTS):
            return ln.strip()
    return None


def _warnings(log: str) -> list[str]:
    out = []
    for ln in log.splitlines():
        if "warning" in ln.lower():
            out.append(ln.strip())
    return out[:8]


# ------------------------------------------------------------ convenience

def solve_net(net: dict[str, Any], stackup: list[dict], board_thickness_mm: float,
              f0_hz: float, **kw) -> tuple[FieldResult, dict[str, Any]]:
    """Adapt a `kicad.parse_board_file()` net dict into a solve.

    `net` = {"name", "segments": [{x1,y1,x2,y2,width_mm,layer,...}], "vias": ..}
    """
    cu_thick = {ly["name"]: float(ly.get("thickness_mm") or 0.035)
                for ly in stackup if ly.get("type") == "copper"}
    segs = []
    for s in net["segments"]:
        w = s.get("width_mm")
        if w is None:
            w = s.get("width_m", 0.3e-3) * 1e3
        segs.append(Segment3D(
            x1=float(s["x1"]), y1=float(s["y1"]),
            x2=float(s["x2"]), y2=float(s["y2"]),
            width_mm=float(w),
            layer=str(s.get("layer", "F.Cu")),
            thickness_mm=cu_thick.get(s.get("layer", "F.Cu"), 0.035),
        ))
    # vias are inferred from layer transitions in `build_fasthenry_input`;
    # the KiCad `vias` count travels through in `meta` for the report only.
    vias: list[Via3D] = []
    inp, meta = build_fasthenry_input(
        net["name"], segs, vias, stackup, board_thickness_mm, f0_hz,
        design_vias=int(net.get("vias") or 0), **kw)
    return run_fasthenry(inp), meta


def convergence_check(net: dict[str, Any], stackup: list[dict],
                      board_thickness_mm: float, f0_hz: float,
                      densities: tuple[int, ...] = (20, 30, 40),
                      tol: float = 0.03) -> dict[str, Any]:
    """Solve at increasing mesh density and report L-drift honestly.

    We report the *last two* points' relative L change as `l_drift`. Above
    `tol` we set `converged=False` and the caller downgrades its uncertainty
    band rather than pretending the number is tight.
    """
    points = []
    for d in densities:
        res, meta = solve_net(net, stackup, board_thickness_mm, f0_hz, seg_density=d)
        points.append({"seg_density": d, "l_h": res.l_h, "r_ohm": res.r_ohm,
                       "filaments": res.filaments, "runtime_s": round(res.runtime_s, 3)})
    if len(points) >= 2:
        a, b = points[-2]["l_h"], points[-1]["l_h"]
        drift = abs(b - a) / a if a else 0.0
    else:
        drift = 0.0
    return {
        "points": points,
        "l_drift": round(drift, 5),
        "converged": drift <= tol,
        "tol": tol,
        "note": ("L converged within tolerance" if drift <= tol else
                 "L still drifting above tolerance — increase seg_density for a tighter number"),
    }


# --------------------------------------------------------------------- TODO
# Tier C (electrostatic C from a real dielectric stackup) is NOT wired yet:
#   FastCap (1992, MIT) builds here but hangs on trivial cases (K&R allocator
#   bugs on 64-bit); FasterCap 6.0.7 Linux binaries need wxWidgets 3.0 which
#   is unavailable on Debian trixie, and source is GPL (see NOTICE.md §3).
# Until that is resolved, capacitance stays Tier A closed-form (always
# labelled as such in the report). This is tracked as T-304 in plan.md.

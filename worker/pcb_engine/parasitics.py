"""Closed-form (Tier A) PCB parasitic kernel.

Physics references (see docs/RESEARCH.md §2):
  * Skin depth                δ = sqrt(2ρ / (ωμ₀)) — Copper ρ ≈ 1.72e-8 Ω·m (20 °C)
  * Microstrip (Hammerstad–Jensen, IPC-2141A family)
  * Symmetric stripline      Z₀ = (60/√εr)·ln(4b / (0.67π(0.8w+t)))
  * Partial inductance       Grover/Rosa rectangular bar (low frequency)
  * Via inductance           L ≈ 2e-7·h·(ln(4h/d) − 1)
  * Skin-effect AC resistance perimeter approximation (±20 %, see report)

Reference-plane determination picks the nearest copper on EITHER side with the
thinnest dielectric gap (mirrors field solving on real 2/4/6-layer stackups).
Everything returned carries method + validity band so the UI/report can display
provenance honestly. Tier B (PEEC, FastHenry2/FasterCap) plugs into the same
dataclasses later (plan T-303/T-304).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

RHO_CU = 1.72e-8                    # Ω·m annealed copper @ 20 °C
EPS0 = 8.8541878128e-12             # F/m
MU0 = 4e-7 * math.pi                # H/m
C0 = 299_792_458.0                  # m/s
OZ1_M = 35e-6                       # 1 oz copper ≈ 35 µm
DEFAULT_ER = 4.3


# ---------------------------------------------------------------- helpers

def skin_depth(f_hz: float, rho: float = RHO_CU) -> float:
    if f_hz <= 0:
        return math.inf
    return math.sqrt(rho / (math.pi * f_hz * MU0))


def microstrip(w: float, h: float, t: float, er: float) -> dict:
    """Surface/embedded microstrip (Hammerstad–Jensen 1980). All SI units."""
    w_h = w / h
    eps_eff = 0.5 * (er + 1) + 0.5 * (er - 1) / math.sqrt(1 + 12 / w_h)
    if w_h <= 1:
        z0 = (60 / math.sqrt(eps_eff)) * math.log(8 / w_h + w_h / 4)
    else:
        z0 = (120 * math.pi / math.sqrt(eps_eff)) / (w_h + 1.393 + 0.667 * math.log(w_h + 1.444))
    z0_ipc = (87 / math.sqrt(er + 1.41)) * math.log(5.98 * h / (0.8 * w + t))
    l_pm = z0 * math.sqrt(eps_eff) / C0
    c_pm = math.sqrt(eps_eff) / (C0 * z0)
    delay_ps_mm = 1e12 * math.sqrt(eps_eff) / C0 * 1e-3
    return {"er_eff": eps_eff, "z0": z0, "z0_ipc2141": z0_ipc,
            "l_per_m": l_pm, "c_per_m": c_pm, "delay_ps_per_mm": delay_ps_mm}


def stripline(w: float, b: float, t: float, er: float) -> dict:
    """Symmetric stripline (IPC-2141A). b = plane-to-plane spacing."""
    z0 = (60 / math.sqrt(er)) * math.log(4 * b / (0.67 * math.pi * (0.8 * w + t)))
    l_pm = z0 * math.sqrt(er) / C0
    c_pm = math.sqrt(er) / (C0 * z0)
    delay_ps_mm = 1e12 * math.sqrt(er) / C0 * 1e-3
    return {"er_eff": er, "z0": z0, "z0_ipc2141": None,
            "l_per_m": l_pm, "c_per_m": c_pm, "delay_ps_per_mm": delay_ps_mm}


def straight_partial_inductance(l: float, w: float, t: float) -> float:
    """Grover/Rosa rectangular filament, current at centroid (low f)."""
    if l <= 0:
        return 0.0
    wt = w + t
    return 2e-7 * l * (math.log(2 * l / wt) + 0.5 + 0.2235 * wt / l)


def via_inductance(h: float, d: float) -> float:
    """Isolated via approximation; with a nearby plane the value is ~25–35 % lower."""
    h = max(h, 1e-6)
    return 2e-7 * h * (math.log(4 * h / d) - 1.0)


def via_capacitance(h: float, d_pad: float = 0.6e-3, d_antipad: float = 1.1e-3,
                    er: float = 4.4) -> float:
    """Via barrel-to-plane capacitance (Howard Johnson's formula, F).

    C_via = 1.41 * er * T * D_1 / (D_2 - D_1) [pF when dims in inches].
    """
    if h <= 0 or d_antipad <= d_pad:
        return 0.0
    h_in = h / 0.0254
    d1_in = d_pad / 0.0254
    d2_in = d_antipad / 0.0254
    return 1.41e-12 * er * h_in * d1_in / (d2_in - d1_in)


def copper_resistivity(temp_c: float = 20.0) -> float:
    """Temperature-adjusted copper resistivity: ρ(T) = ρ_20 * (1 + α_Cu * (T - 20))."""
    alpha_cu = 0.00393
    return RHO_CU * (1.0 + alpha_cu * (temp_c - 20.0))


def ipc2152_ampacity(w_m: float, t_m: float, delta_t_c: float = 20.0,
                     external: bool = True) -> float:
    """IPC-2152 trace current-carrying capacity (A) for a given ΔT (°C)."""
    if w_m <= 0 or t_m <= 0 or delta_t_c <= 0:
        return 0.0
    area_mils2 = (w_m / 2.54e-5) * (t_m / 2.54e-5)
    k = 0.048 if external else 0.024
    return k * (delta_t_c ** 0.44) * (area_mils2 ** 0.725)


def emi_metrics(
    l_loop_h: float,
    c_sw_f: float,
    f_hz: float,
    i_sw_a: float = 10.0,
    dv_dt_v_ns: float = 20.0,
    loop_area_m2: float = 1e-4,
    dist_m: float = 3.0,
) -> dict[str, float]:
    """Power-electronics EMI metrics: DM radiated field, CM dv/dt current, and ringing."""
    # Differential-mode radiated E-field (V/m) at distance dist_m:
    # E_DM = 1.316e-14 * I * A * f^2 / r
    e_dm_v_m = 1.316e-14 * abs(i_sw_a) * max(loop_area_m2, 0.0) * (f_hz ** 2) / max(dist_m, 0.1)
    e_dm_dbuv_m = 20.0 * math.log10(max(e_dm_v_m * 1e6, 1e-12))

    # Common-mode displacement current: I_CM = C_sw * (dv/dt)
    i_cm_a = max(c_sw_f, 0.0) * (abs(dv_dt_v_ns) * 1e9)

    # Commutation loop ringing frequency & characteristic impedance
    if l_loop_h > 0 and c_sw_f > 0:
        f_ring_hz = 1.0 / (2.0 * math.pi * math.sqrt(l_loop_h * c_sw_f))
        z_ring_ohm = math.sqrt(l_loop_h / c_sw_f)
    else:
        f_ring_hz = 0.0
        z_ring_ohm = 0.0

    return {
        "e_dm_v_m": e_dm_v_m,
        "e_dm_dbuv_m": e_dm_dbuv_m,
        "i_cm_a": i_cm_a,
        "f_ring_hz": f_ring_hz,
        "z_ring_ohm": z_ring_ohm,
    }


def dc_resistance(length: float, w: float, t: float, rho: float = RHO_CU) -> float:
    return rho * length / (w * t)


def huray_roughness_factor(f_hz: float, a_um: float = 0.5, sr: float = 1.2,
                           rho: float = RHO_CU) -> float:
    """Huray snowball conductor surface roughness correction factor (K_rough).

    Unlike Hammerstad-Jensen (which saturates at 2x), the Huray model
    accurately predicts 2.5-3.5x loss at GHz frequencies for standard ED foil.
    """
    delta = skin_depth(f_hz, rho)
    if math.isinf(delta) or a_um <= 0 or sr <= 0:
        return 1.0
    a = a_um * 1e-6
    ratio = delta / a
    return 1.0 + 1.5 * sr / (1.0 + ratio + 0.5 * ratio * ratio)


def ac_resistance(length: float, w: float, t: float, f_hz: float,
                  rho: float = RHO_CU, roughness_um: float = 1.0,
                  roughness_model: str = "huray") -> float:
    """Perimeter skin-effect approximation with Huray or Hammerstad-Jensen roughness.

    A_eff = min(w·t, perimeter·δ), scaled by K_sr.
    Proximity effect is NOT included (needs PEEC); treat result as ±20 %
    for parallel high-di/dt runs — the report says so explicitly.
    """
    delta = skin_depth(f_hz, rho)
    if math.isinf(delta):
        return dc_resistance(length, w, t, rho)
    perimeter = 2.0 * (w + t)
    area = min(w * t, perimeter * delta)
    r_smooth = rho * length / area
    if roughness_um > 0:
        if roughness_model == "huray":
            return r_smooth * huray_roughness_factor(f_hz, a_um=roughness_um * 0.5, rho=rho)
        rq = roughness_um * 1e-6
        k_sr = 1.0 + (2.0 / math.pi) * math.atan(1.4 * (rq / delta) ** 2)
        return r_smooth * k_sr
    return r_smooth


def dielectric_conductance(c_f: float, f_hz: float, tan_d: float = 0.02) -> float:
    """Parallel dielectric loss conductance G_d = ω · C · tan(δ) (S)."""
    if c_f <= 0 or f_hz <= 0 or tan_d <= 0:
        return 0.0
    return 2.0 * math.pi * f_hz * c_f * tan_d


def djordjevic_sarkar(
    f_hz: float,
    er_spec: float = 4.4,
    tan_d_spec: float = 0.02,
    f_spec: float = 1e9,
    f1: float = 1e3,
    f2: float = 1e12,
) -> tuple[float, float]:
    """Kramers-Kronig causal wideband dielectric model (Djordjevic-Sarkar).

    Returns (er_real(f), tan_delta(f)) fitted to (er_spec, tan_d_spec) at f_spec.
    """
    if f_hz <= 0 or tan_d_spec <= 0:
        return er_spec, max(tan_d_spec, 0.0)
    k = math.log10(f2 / f1)
    # Fit delta_eps from imaginary part at f_spec:
    # Im(log10((f2 + j*f)/(f1 + j*f))) = (atan(f/f2) - atan(f/f1)) / ln(10)
    im_spec = (math.atan(f_spec / f2) - math.atan(f_spec / f1)) / math.log(10.0)
    delta_eps = (-er_spec * tan_d_spec * k) / im_spec if abs(im_spec) > 1e-15 else 0.0
    re_spec = 0.5 * math.log10((f2 * f2 + f_spec * f_spec) / (f1 * f1 + f_spec * f_spec))
    eps_inf = er_spec - (delta_eps / k) * re_spec

    re_f = 0.5 * math.log10((f2 * f2 + f_hz * f_hz) / (f1 * f1 + f_hz * f_hz))
    im_f = (math.atan(f_hz / f2) - math.atan(f_hz / f1)) / math.log(10.0)
    er_f = eps_inf + (delta_eps / k) * re_f
    ei_f = -(delta_eps / k) * im_f
    return er_f, (ei_f / er_f if er_f > 0 else tan_d_spec)


def plane_capacitance(er: float, area_m2: float, d_m: float) -> float:
    return er * EPS0 * area_m2 / d_m


# ------------------------------------------------------- stackup geometry

def _copper_indices(stackup: list[dict]) -> list[int]:
    return [i for i, ly in enumerate(stackup) if ly["type"] == "copper"]


def dielectric_between(stackup: list[dict], i_lo: int, i_hi: int) -> tuple[float, float]:
    """(thickness [m], εr) of dielectrics strictly between copper indices i_lo < i_hi."""
    total_t = 0.0
    er_num = 0.0
    for ly in stackup[i_lo + 1:i_hi]:
        if ly["type"] == "copper":
            continue
        t = ly.get("thickness_mm") or 0.2
        er = ly.get("epsilon_r") or DEFAULT_ER
        total_t += t
        er_num += t * er
    if total_t <= 0:
        return 0.0, DEFAULT_ER
    return total_t * 1e-3, er_num / total_t


def _layer_gap(stackup: list[dict], me: int, other: int) -> tuple[float, float]:
    lo, hi = (me, other) if me < other else (other, me)
    h, er = dielectric_between(stackup, lo, hi)
    if h == 0.0:  # stapled copper arts — invent small gap so formulas stay finite
        h = 0.2e-3
    return h, er


def nearest_reference(stackup: list[dict], layer_name: str) -> dict | None:
    """Nearest copper layer to `layer_name` on either side, thinnest gap wins."""
    idx_of = {ly["name"]: i for i, ly in enumerate(stackup)}
    me = idx_of.get(layer_name)
    if me is None:
        return None
    best = None
    for i in _copper_indices(stackup):
        if i == me:
            continue
        h, er = _layer_gap(stackup, me, i)
        cand = {"index": i, "name": stackup[i]["name"], "gap_m": h, "er": er,
                "side": "below" if i > me else "above"}
        if best is None or h < best["gap_m"]:
            best = cand
    return best


def _nearest_on_side(stackup: list[dict], me: int, side: str) -> dict | None:
    best = None
    for i in _copper_indices(stackup):
        if side == "above" and i < me:
            h, er = _layer_gap(stackup, i, me)
            cand = {"name": stackup[i]["name"], "gap_m": h, "er": er}
            if best is None or h < best["gap_m"]:
                best = cand
        elif side == "below" and i > me:
            h, er = _layer_gap(stackup, me, i)
            cand = {"name": stackup[i]["name"], "gap_m": h, "er": er}
            if best is None or h < best["gap_m"]:
                best = cand
    return best


# ------------------------------------------------------- net-level analysis

@dataclass
class NetParasitics:
    name: str
    total_length_mm: float
    avg_width_mm: float
    ref_plane: str | None
    height_mm: float | None
    er: float
    copper_m: float
    r_dc: float
    r_ac: float
    l_h: float
    c_f: float
    z0: float | None
    er_eff: float | None
    vias: int
    l_via_total_h: float
    r_via_total_ohm: float
    method: str = "Tier A — closed-form"
    uncertainty: str = "±5–10 % (geometry & stackup permitting)"
    notes: list[str] = field(default_factory=list)


def analyze_net(name: str, segments: list[dict], via_count: int, via_h: float,
                via_d: float, stackup: list[dict], f0: float,
                copper_override_m: float | None = None) -> NetParasitics:
    """segments: [{length_m, width_m, layer}]. Stackup from KiCad parse."""
    total_len = sum(s["length_m"] for s in segments)
    if total_len <= 0:
        raise ValueError(f"net {name!r} has zero tracked length")
    notes: list[str] = []

    cu = {ly["name"]: ly.get("thickness_mm") for ly in stackup if ly["type"] == "copper"}
    avg_w = sum(s["width_m"] * s["length_m"] for s in segments) / total_len

    r_dc = r_ac = l_h = c_f = 0.0
    ref_plane_name = None
    h_ref_m = None
    z0_used = None
    er_eff_used = None
    er_used = DEFAULT_ER
    idx_of = {ly["name"]: i for i, ly in enumerate(stackup)}
    for s in segments:
        t_mm = cu.get(s["layer"]) or 0.035
        t = copper_override_m if copper_override_m is not None else t_mm * 1e-3
        w = s["width_m"]
        r_dc += dc_resistance(s["length_m"], w, t)
        r_ac += ac_resistance(s["length_m"], w, t, f0)

        me = idx_of.get(s["layer"])
        up = _nearest_on_side(stackup, me, "above") if me is not None else None
        dn = _nearest_on_side(stackup, me, "below") if me is not None else None

        if up and dn:  # buried between references → symmetric stripline, b = gap_up + trace + gap_dn
            b = up["gap_m"] + dn["gap_m"] + t
            lz = stripline(w, b, t, (up["er"] * up["gap_m"] + dn["er"] * dn["gap_m"]) / (up["gap_m"] + dn["gap_m"]))
            plane = dn if dn["gap_m"] <= up["gap_m"] else up
        elif dn:
            lz = microstrip(w, dn["gap_m"], t, dn["er"])
            plane = dn
        elif up:
            lz = microstrip(w, up["gap_m"], t, up["er"])
            plane = up
        else:
            lz = None
            plane = None

        if lz is not None:
            l_h += lz["l_per_m"] * s["length_m"]
            c_f += lz["c_per_m"] * s["length_m"]
            if z0_used is None:
                z0_used, er_eff_used = lz["z0"], lz["er_eff"]
                ref_plane_name, h_ref_m, er_used = plane["name"], plane["gap_m"], plane["er"]
        else:
            l_h += straight_partial_inductance(s["length_m"], w, t)
            notes.append(f"{s['layer']}: no copper reference — C omitted for this segment")

    l_via = via_inductance(via_h, via_d) * via_count
    delta = skin_depth(f0)
    area = math.pi * via_d * min(via_d / 4.0, delta)
    r_via = (RHO_CU * via_h / area) * via_count if via_count else 0.0

    return NetParasitics(
        name=name,
        total_length_mm=total_len * 1e3,
        avg_width_mm=avg_w * 1e3,
        ref_plane=ref_plane_name,
        height_mm=(h_ref_m * 1e3 if h_ref_m else None),
        er=er_used,
        copper_m=35e-6 if copper_override_m is None else copper_override_m,
        r_dc=r_dc,
        r_ac=r_ac,
        l_h=l_h + l_via,
        c_f=c_f,
        z0=z0_used,
        er_eff=er_eff_used,
        vias=via_count,
        l_via_total_h=l_via,
        r_via_total_ohm=r_via,
        notes=notes,
    )


def impedance_sweep(r: float, l_h: float, c_f: float, ref_node_c: bool = True,
                    n: int = 90, fmin: float = 1e2, fmax: float = 1e9,
                    tan_d: float = 0.02) -> dict:
    """log-spaced |Z(f)| of the injected R–L(+C//G_d to ref) network (for the UI chart)."""
    fs, zs = [], []
    for i in range(n):
        f = fmin * (fmax / fmin) ** (i / (n - 1))
        xl = 2 * math.pi * f * l_h
        z = complex(r, xl)
        if ref_node_c and c_f > 0:
            er_f, td_f = djordjevic_sarkar(f, tan_d_spec=tan_d)
            c_eff = c_f * (er_f / 4.4)
            yc = complex(dielectric_conductance(c_eff, f, td_f), 2 * math.pi * f * c_eff)
            zc = 1.0 / yc
            z = (z * zc) / (z + zc)
        fs.append(f)
        zs.append(abs(z))
    return {"f_hz": fs, "z_ohm": zs}

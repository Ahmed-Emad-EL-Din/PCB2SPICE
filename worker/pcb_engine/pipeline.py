"""End-to-end orchestration: PCB design + QSPICE project → parasitic-injected zip + report.

Safety rails:
  * zip-slip / path traversal rejected (`_safe_names`)
  * total uncompressed size + per-file limits (configurable)
  * SPICE-like detection before rewriting; KiCad s-expression netlists are left untouched
  * .qsch injection is additive-only; .cir is rewritten atomically (new bytes)
  * idempotency guard in `cir.transform`
"""
from __future__ import annotations

import datetime as _dt
import difflib
import io
import json
import math
import re
import zipfile
from typing import Any

from . import __version__, cir, field, kicad, parasitics, qsch, report

MAX_FILES = 400
MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024
MAX_SINGLE_FILE = 64 * 1024 * 1024

STRONG_EXTS = {".cir", ".sp", ".spice"}
WEAK_EXTS = {".net", ".lib", ".txt"}
SPICE_EXTS = STRONG_EXTS | WEAK_EXTS
QSCH_EXTS = {".qsch"}
ZERO_NETS = {"0", "gnd", "agnd", "dgnd", "pgnd", "vss"}

# heuristic power-electronics net classifier (flagged ONLY as suggestion; user confirms)
_CRITICAL_PATTERNS = [
    (re.compile(r"(^|_|\b)(sw|ph|switch|phase|swnode|sw_node|hx)(_|\b)", re.I), "switching node — highest dv/dt in the converter"),
    (re.compile(r"(gnd|pgnd|agnd|vss).*(sw|switch)|(sw|switch).*(gnd|pgnd|agnd)", re.I), "switch-to-ground loop — critical commutation path"),
    (re.compile(r"(gate|gdrv|g_dr|gd|lg|hg|q\d+g)", re.I), "gate-drive loop — high di/dt, sensitive to L"),
    (re.compile(r"(vin|vbus|bulk|hvin|hv)", re.I), "input bulk rail — high di/dt during commutation"),
]


class PipelineError(Exception):
    pass


def _safe_names(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    if len(names) > MAX_FILES:
        raise PipelineError(f"project has {len(names)} files (limit {MAX_FILES})")
    total = 0
    out = []
    for n in names:
        norm = n.replace("\\", "/")
        parts = norm.split("/")
        if norm.startswith("/") or ".." in parts:
            raise PipelineError(f"unsafe path in archive: {n!r}")
        info = zf.getinfo(n)
        if info.file_size > MAX_SINGLE_FILE:
            raise PipelineError(f"file too large: {n!r}")
        total += info.file_size
        out.append(norm)
    if total > MAX_TOTAL_UNCOMPRESSED:
        raise PipelineError("archive uncompressed size exceeds 256 MB limit")
    return out


def _is_probably_spice(path: str, data: bytes) -> bool:
    """Strong netlist extensions are trusted; weak ones need ≥2 netlist signals.

    KiCad s-expression netlists always start with '(' and are never touched.
    """
    head = data[:4096].lstrip()
    if head.startswith(b"("):
        return False
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in STRONG_EXTS:
        return True
    if ext not in WEAK_EXTS and ext != "":
        return False
    text = head.decode("latin-1", errors="ignore").lower()
    signals = (".end", ".subckt", ".model", ".include", ".tran", ".ac ", ".dc ", ".ic ",
               "v(", "i(", ".param", ".meas", "rpar", "x1 ")
    hits = sum(1 for s in signals if s in text)
    return hits >= 2


def classify_net(name: str) -> str | None:
    for pat, reason in _CRITICAL_PATTERNS:
        if pat.search(name):
            return reason
    return None


def default_selection(nets: list[dict[str, Any]]) -> list[str]:
    crit = [n["name"] for n in nets if n.get("critical")]
    if crit:
        return crit
    # fall back: longest routed power net
    if nets:
        return [max(nets, key=lambda n: n["total_length_mm"])["name"]]
    return []


def analyze(pcb_bytes: bytes, pcb_name: str, f0_hz: float = 50e6,
            tier: str = "auto", field_nets: list[str] | None = None,
            seg_density: int = 30) -> dict[str, Any]:
    """Extract parasitics for every net.

    tier:
      "A"    — closed-form only (fast, always available)
      "auto" — closed-form for all nets + Tier B field solve on the critical /
               selected nets when a FastHenry binary is present (default)
      "B"    — Tier B for every net; raises if FastHenry is unavailable
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile("wb", suffix=".kicad_pcb", delete=False) as fh:
        fh.write(pcb_bytes)
        tmp = fh.name
    try:
        parsed = kicad.parse_board_file(tmp)
    except Exception as exc:
        raise PipelineError(f"could not parse KiCad board: {exc}") from exc
    finally:
        os.unlink(tmp)

    stackup = kicad.stackup_for_kernel(parsed["stackup"])
    height_mm = parsed["laminate_height_mm"]
    h_via = height_mm * 1e-3

    nets_out: list[dict[str, Any]] = []
    for net in parsed["nets"]:
        if net["name"].strip().lower() in ZERO_NETS or net["name"] == "":
            continue
        try:
            np_ = parasitics.analyze_net(
                net["name"], net["segments"], net["vias"], h_via,
                net["via_drill_mm"] * 1e-3, stackup, f0_hz)
        except ValueError:
            continue
        sweep = parasitics.impedance_sweep(np_.r_ac + np_.r_via_total_ohm, np_.l_h, np_.c_f)
        crit_reason = classify_net(net["name"])
        nets_out.append({
            "name": np_.name,
            "total_length_mm": round(np_.total_length_mm, 2),
            "avg_width_mm": round(np_.avg_width_mm, 3),
            "ref_plane": np_.ref_plane,
            "height_mm": (round(np_.height_mm, 3) if np_.height_mm else None),
            "r_dc": np_.r_dc,
            "r_ac": np_.r_ac + np_.r_via_total_ohm,
            "l_h": np_.l_h,
            "c_f": np_.c_f,
            "z0": np_.z0,
            "er_eff": np_.er_eff,
            "vias": np_.vias,
            "l_via_total_h": np_.l_via_total_h,
            "critical": bool(crit_reason),
            "critical_reason": crit_reason,
            "segments": len(net["segments"]),
            "method": np_.method,
            "uncertainty": np_.uncertainty,
            "notes": np_.notes,
            "impedance_sweep": sweep,
        })
    nets_out.sort(key=lambda n: (not n["critical"], -n["total_length_mm"]))
    critical = [n["name"] for n in nets_out if n["critical"]]

    # ---- Tier B field solve (non-silent, opt-in by tier/availability) ----
    tier_req = (tier or "auto").strip().upper()
    sinfo = field.solver_info()
    target = set(field_nets or [])
    if tier_req in ("A", "AUTO"):
        # auto: solve the critical nets unless the caller named specific ones
        names = target or ({n["name"] for n in nets_out if n["critical"]} if tier_req == "AUTO" else set())
    elif tier_req == "B":
        names = target or {n["name"] for n in nets_out}
    else:
        raise PipelineError(f"unknown tier {tier!r} (use A, auto or B)")

    field_summary = {"requested_tier": tier_req, "solver": sinfo,
                     "solved": [], "skipped": [], "fallback_reason": None}
    if names and not sinfo["tier_b_available"]:
        msg = ("Tier B requested but no FastHenry binary found "
               "(set FH_BIN or install fasthenry — see docs/TIER-B.md). "
               "All numbers below are Tier A closed-form.")
        field_summary["fallback_reason"] = msg
        if tier_req == "B":
            raise PipelineError(msg)
        analysis_warnings_extra = [msg]
    else:
        analysis_warnings_extra = []

    if names and sinfo["tier_b_available"]:
        by_name = {n["name"]: n for n in parsed["nets"]}
        for nm in sorted(names):
            if nm not in by_name:
                field_summary["skipped"].append({"net": nm, "reason": "not present in the board"})
                continue
            try:
                conv = field.convergence_check(
                    by_name[nm], stackup, parsed["laminate_height_mm"], f0_hz,
                    densities=(20, 30, 45))
                best = max(conv["points"], key=lambda pt: pt["seg_density"])
                # final authoritative solve at the finest density
                res, meta = field.solve_net(
                    by_name[nm], stackup, parsed["laminate_height_mm"], f0_hz,
                    seg_density=best["seg_density"])
            except (field.FieldSolverError, field.FieldSolverUnavailable) as exc:
                field_summary["skipped"].append({"net": nm, "reason": str(exc)})
                continue
            target_net = next(n for n in nets_out if n["name"] == nm)
            target_net["tier_b"] = {
                "r_ohm": res.r_ohm,
                "l_h": res.l_h,
                "f_hz": res.f_hz,
                "solver": res.solver,
                "filaments": res.filaments,
                "meshes": res.meshes,
                "runtime_s": round(res.runtime_s, 3),
                "convergence": conv,
                "geometry": meta,
                "warnings": res.warnings,
                "delta_vs_tier_a": {
                    "r_pct": round((res.r_ohm - target_net["r_ac"]) / target_net["r_ac"] * 100, 1)
                             if target_net["r_ac"] else None,
                    "l_pct": round((res.l_h - target_net["l_h"]) / target_net["l_h"] * 100, 1)
                             if target_net["l_h"] else None,
                },
            }
            field_summary["solved"].append(nm)

    tier_effective = "B" if all(n.get("tier_b") for n in nets_out if n["name"] in names) and names else "A"

    return {
        "tier_requested": tier_req,
        "tier_effective": tier_effective,
        "field": field_summary,
        "ok": True,
        "engine_version": __version__,
        "f0_hz": f0_hz,
        "stackup": stackup,
        "laminate_height_mm": parsed["laminate_height_mm"],
        "total_nets_in_design": parsed["total_nets_in_design"],
        "footprints": parsed["footprints"],
        "zones": parsed["zones"],
        "nets": nets_out,
        "default_selection": default_selection(nets_out),
        "critical_nets": critical,
        "warnings": (["No critical switching nets detected by heuristic — review selection manually"]
                     if nets_out and not critical else []) + analysis_warnings_extra,
    }


def _net_payload(analysis: dict[str, Any], selected: list[str]) -> dict[str, Any]:
    """Values that get written into parasitics.lib.

    When a Tier B field solve exists for the net we inject THAT R and L
    (finite-plane, proximity-aware) and keep the closed-form C — capacitance
    has no field solver in this release, so it stays labelled Tier A rather
    than being silently passed off as solved.
    """
    chosen = [n for n in analysis["nets"] if n["name"] in set(selected)]
    out = []
    for n in chosen:
        tb = n.get("tier_b")
        if tb:
            out.append({
                "name": n["name"], "r_ohm": tb["r_ohm"], "l_h": tb["l_h"],
                "c_f": n["c_f"], "f0_hz": analysis["f0_hz"],
                "method": f"Tier B — FastHenry2 field solve ({tb['filaments']} filaments; "
                          f"L-delta over mesh sweep {tb['convergence']['l_drift']*100:.1f}%)",
                "uncertainty": (f"±{max(2.0, tb['convergence']['l_drift']*100):.0f}% L (±5–10 % C, closed-form)"
                                if tb["convergence"]["converged"] else
                                f"⚠ L not converged on this mesh ({tb['convergence']['l_drift']*100:.1f} % drift) "
                                f"— increase seg_density"),
                "tier": "B", "tier_b": tb,
            })
        else:
            out.append({
                "name": n["name"], "r_ohm": n["r_ac"], "l_h": n["l_h"], "c_f": n["c_f"],
                "f0_hz": analysis["f0_hz"], "method": n["method"],
                "uncertainty": n["uncertainty"], "tier": "A",
            })
    return {"nets": out, "mutuals": [], "tier": analysis.get("tier_effective", "A")}


def inject(project_zip: bytes | None, cir_text: str | None, qsch_bytes: bytes | None,
           analysis: dict[str, Any], selected_nets: list[str],
           ref_node: str, design_name: str, source_file: str) -> dict[str, Any]:
    if not selected_nets:
        raise PipelineError("select at least one net to inject")
    payload = _net_payload(analysis, selected_nets)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    files_changed: list[dict[str, str]] = []
    out_zip_io = io.BytesIO()
    diff_text = ""
    transformed_dirs: set[str] = set()
    total_stats = {"nets": 0, "elements_added": 0, "lines_before": 0, "lines_after": 0,
                   "r_added": 0, "l_added": 0, "c_added": 0, "k_added": 0}

    if project_zip is not None:
        src = io.BytesIO(project_zip)
        try:
            zin = zipfile.ZipFile(src)
        except zipfile.BadZipFile as exc:
            raise PipelineError("project archive is not a valid .zip") from exc
        names = _safe_names(zin)
        with zipfile.ZipFile(out_zip_io, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                path = name
                lower = path.lower()
                data = zin.read(name)
                if lower.endswith(tuple(SPICE_EXTS)) and _is_probably_spice(lower, data):
                    try:
                        text = data.decode("utf-8", errors="strict")
                    except UnicodeDecodeError:
                        text = data.decode("latin-1")
                    try:
                        new_text, diff, stats = cir.transform(text, payload, ref_node)
                    except ValueError as exc:
                        files_changed.append({"path": path, "action": "skipped", "detail": str(exc)})
                        zout.writestr(path, data)
                        continue
                    zout.writestr(path, new_text.encode("utf-8"))
                    if not diff_text:
                        diff_text = diff
                    d = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
                    transformed_dirs.add(d)
                    for k in total_stats:
                        total_stats[k] += stats.get(k, 0)
                    files_changed.append({"path": path, "action": "transformed",
                                          "detail": f"+{stats['elements_added']} elements, {stats['lines_before']}→{stats['lines_after']} lines"})
                elif lower.endswith(".qsch"):
                    try:
                        summary = [f"{n['name']}: R={n['r_ohm']:.4g}Ω L={n['l_h']*1e9:.4g}nH "
                                   f"C={n['c_f']*1e12:.4g}pF" for n in payload["nets"]]
                        new_bytes = qsch.inject(data, "parasitics.lib", summary, stamp)
                    except qsch.QschError as exc:
                        files_changed.append({"path": path, "action": "skipped", "detail": str(exc)})
                        zout.writestr(path, data)
                        continue
                    zout.writestr(path, new_bytes)
                    files_changed.append({"path": path, "action": "additive-inject",
                                          "detail": ".include parasitics.lib + provenance block appended (original geometry untouched)"})
                elif lower.endswith("parasitics.lib"):
                    continue  # replaced below
                else:
                    zout.writestr(path, data)
            zout.writestr("parasitics.lib", cir.generate_library(payload, ref_node))
            files_changed.append({"path": "parasitics.lib", "action": "generated",
                                  "detail": "provenance-annotated parasitic library"})
            for d in sorted(transformed_dirs):
                if d and d != "":
                    zout.writestr(d + "parasitics.lib", cir.generate_library(payload, ref_node))
                    files_changed.append({"path": d + "parasitics.lib", "action": "generated",
                                          "detail": "co-located include for nested SPICE file"})
            meta_doc = {
                "tool": "pcb-parasitic-qspice",
                "engine_version": __version__,
                "generated_utc": stamp,
                "design": design_name,
                "solver_tier": analysis.get("tier_effective", "A"),
                "solver_detail": [{"net": n["name"],
                                   "tier": n.get("tier", "A"),
                                   "method": n.get("method")} for n in payload["nets"]],
                "solver_info": field.solver_info(),
                "f0_hz": analysis["f0_hz"],
                "reference_node": ref_node,
                "nets": [{"name": n["name"], "r_ohm": n["r_ohm"], "l_h": n["l_h"], "c_f": n["c_f"]}
                         for n in payload["nets"]],
            }
            zout.writestr("parasitics-meta.json", json.dumps(meta_doc, indent=2))
            files_changed.append({"path": "parasitics-meta.json", "action": "generated",
                                  "detail": "machine-readable provenance manifest"})
        out_zip = out_zip_io.getvalue()
    else:
        # single-file mode: build a fresh project zip from whatever was provided
        with zipfile.ZipFile(out_zip_io, "w", zipfile.ZIP_DEFLATED) as zout:
            if cir_text is not None:
                new_text, diff, stats = cir.transform(cir_text, payload, ref_node)
                zout.writestr("circuit-parasitic.cir", new_text)
                diff_text = diff
                for k in total_stats:
                    total_stats[k] += stats.get(k, 0)
                files_changed.append({"path": "circuit-parasitic.cir", "action": "transformed",
                                      "detail": f"+{stats['elements_added']} elements"})
            if qsch_bytes is not None:
                summary = [f"{n['name']}: R={n['r_ohm']:.4g}Ω L={n['l_h']*1e9:.4g}nH C={n['c_f']*1e12:.4g}pF"
                           for n in payload["nets"]]
                zout.writestr("circuit-parasitic.qsch", qsch.inject(qsch_bytes, "parasitics.lib", summary, stamp))
                files_changed.append({"path": "circuit-parasitic.qsch", "action": "additive-inject",
                                      "detail": ".include parasitics.lib appended (additive-only)"})
            zout.writestr("parasitics.lib", cir.generate_library(payload, ref_node))
            files_changed.append({"path": "parasitics.lib", "action": "generated", "detail": "provenance library"})
        out_zip = out_zip_io.getvalue()

    nets_by_name = {n["name"]: n for n in analysis["nets"]}
    chart_net = nets_by_name.get(selected_nets[0])
    injection = {"selected_nets": selected_nets, "stats": total_stats, "files_changed": files_changed}
    report_html = report.build_report(
        {"design_name": design_name, "source_file": source_file,
         "chart_net": chart_net["name"] if chart_net else None},
        analysis, injection, stamp)
    # append report into the zip as well (rebuild with it)
    final_io = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(out_zip)) as zin, zipfile.ZipFile(final_io, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("PARASITICS-REPORT.html", report_html)
    return {"zip_bytes": final_io.getvalue(), "diff": diff_text,
            "stats": total_stats, "files_changed": files_changed, "report_html": report_html}

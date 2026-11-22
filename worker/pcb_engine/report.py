"""Self-contained HTML engineering report (inline CSS/SVG — no external assets)."""
from __future__ import annotations

import datetime as _dt
import html
from typing import Any

ACCENT = "#0e7490"   # deep teal
INK = "#0f172a"      # slate-900
MUTE = "#64748b"     # slate-500
BG = "#f8fafc"


def _fmt(v: float, unit: str, scale: float = 1.0, digits: int = 3) -> str:
    if v is None:
        return "—"
    return f"{v*scale:,.{digits}f} {unit}"


def _impedance_svg(sweep: dict[str, list[float]], width: int = 640, height: int = 180) -> str:
    f, z = sweep["f_hz"], sweep["z_ohm"]
    if not f:
        return ""
    import math
    lf = [math.log10(v) for v in f]
    lz = [math.log10(max(v, 1e-6)) for v in z]
    x0, x1, y0, y1 = min(lf), max(lf), min(lz), max(lz)
    pad_l, pad_r, pad_t, pad_b = 46, 10, 12, 30
    iw, ih = width - pad_l - pad_r, height - pad_t - pad_b

    def X(i: int) -> float:
        return pad_l + (lf[i] - x0) / max(x1 - x0, 1e-9) * iw

    def Y(i: int) -> float:
        return pad_t + (1 - (lz[i] - y0) / max(y1 - y0, 1e-9)) * ih

    pts = " ".join(f"{X(i):.1f},{Y(i):.1f}" for i in range(len(f)))
    # decade gridlines + labels
    grid = []
    g = math.ceil(x0)
    while g <= x1 + 1e-9:
        xp = pad_l + (g - x0) / max(x1 - x0, 1e-9) * iw
        grid.append(f'<line x1="{xp:.1f}" y1="{pad_t}" x2="{xp:.1f}" y2="{pad_t+ih}" stroke="#e2e8f0"/>'
                    f'<text x="{xp:.1f}" y="{height-12}" font-size="9" fill="{MUTE}" text-anchor="middle">1e{int(round(g))}</text>')
        g += 1
    ytext = (f'<text x="12" y="{pad_t+8}" font-size="9" fill="{MUTE}">Ω (log)</text>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="|Z| vs frequency">'
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff" stroke="#e2e8f0" rx="8"/>'
            + "".join(grid) + ytext +
            f'<polyline points="{pts}" fill="none" stroke="{ACCENT}" stroke-width="2.25" stroke-linejoin="round"/>'
            f'<text x="{width-pad_r}" y="{pad_t+2}" font-size="9" fill="{MUTE}" text-anchor="end">|Z(f)|</text>'
            f'</svg>')


def build_report(meta: dict[str, Any], analysis: dict[str, Any],
                 injection: dict[str, Any] | None, stamp: str) -> str:
    e = html.escape
    nets = analysis["nets"]
    sel_names = set(injection["selected_nets"]) if injection else {n["name"] for n in nets}
    any_b = any(n.get("tier_b") for n in nets)
    rows = []
    for n in nets:
        star = " ◆" if n.get("critical") else ""
        tb = n.get("tier_b")
        rows.append(
            "<tr>"
            f"<td class='mono'>{e(n['name'])}{star}</td>"
            f"<td>{n['total_length_mm']:.1f}</td>"
            f"<td>{n['avg_width_mm']:.2f}</td>"
            f"<td>{e(str(n.get('ref_plane') or '—'))}</td>"
            f"<td class='mono'>{n['r_ac']*1e3:.2f} m</td>"
            f"<td class='mono'>{n['l_h']*1e9:.3f}</td>"
            + (f"<td class='mono b'>{tb['r_ohm']*1e3:.2f} m</td>"
               f"<td class='mono b'>{tb['l_h']*1e9:.3f}</td>"
               f"<td class='mono b'>{tb['delta_vs_tier_a']['l_pct']:+.1f}%</td>" if tb else
               ("<td class='muted'>—</td><td class='muted'>—</td><td class='muted'>—</td>" if any_b else ""))
            + f"<td class='mono'>{n['c_f']*1e12:.3f}</td>"
            f"<td class='mono'>{n['z0']:.1f}" + (" Ω" if n['z0'] else "") + "</td>"
            f"<td>{n['vias']}</td>"
            "</tr>")
    n_b = sum(1 for n in nets if n.get("tier_b"))
    if n_b == len(nets) and nets:
        solver_line = f"Tier B — FastHenry2 field solve ({n_b} net{'s' if n_b != 1 else ''})"
    elif n_b:
        solver_line = (f"Tier A closed-form (all nets) + Tier B field solve "
                       f"({n_b} of {len(nets)} nets)")
    else:
        solver_line = "Tier A — closed-form (no field solver available)"
    chart_net = next((n for n in nets if n["name"] == meta.get("chart_net")), nets[0] if nets else None)
    chart = _impedance_svg(chart_net["impedance_sweep"]) if chart_net and chart_net.get("impedance_sweep") else ""

    tb_nets = [n for n in nets if n.get("tier_b")]
    tb_html = ""
    if tb_nets:
        tb_rows = []
        for n in tb_nets:
            tb = n["tier_b"]
            conv = tb["convergence"]
            pts = "".join(f"<span class='chip'>{pt['seg_density']}: {pt['l_h']*1e9:.3f}</span>"
                          for pt in conv["points"])
            ok = conv["converged"]
            badge = ("<span class='ok'>converged</span>" if ok
                     else "<span class='bad'>NOT converged</span>")
            tb_rows.append(
                "<tr>"
                f"<td class='mono'>{e(n['name'])}</td>"
                f"<td class='mono'>{tb['r_ohm']*1e3:.2f} mΩ</td>"
                f"<td class='mono'>{tb['l_h']*1e9:.3f} nH</td>"
                f"<td class='mono'>{tb['delta_vs_tier_a']['l_pct']:+.1f} %</td>"
                f"<td class='mono'>{tb['filaments']:,}</td>"
                f"<td class='mono'>{tb['runtime_s']:.2f} s</td>"
                f"<td>{badge}<br><span class='mono tiny'>{conv['l_drift']*100:.1f} % drift</span></td>"
                f"<td>{pts}</td>"
                "</tr>")
        tb_html = f"""
<h2>2b · Tier B field solve — FastHenry2 (finite plane, proximity-aware)</h2>
<div class="callout"><b>Why B differs from A.</b> Tier A treats each trace as a microstrip over an
<i>infinite</i> plane directly beneath it. Tier B builds the real finite geometry — every trace segment,
every via, and the nearest copper plane as a meshed sheet — and solves the magneto-quasistatic mesh
formulation. Where the return current cannot stay directly under the trace (plane edges, layer changes
through a single via, long loops) Tier B reports a <b>larger</b> loop inductance, because that is what
the copper actually does. The injected netlist uses the <b>Tier B</b> R and L when available; C stays
closed-form (no electrostatic solver in this release).</div>
<table><thead><tr><th>Net</th><th>R</th><th>L</th><th>Δ L vs A</th><th>Filaments</th><th>Solve time</th>
<th>Mesh convergence</th><th>L (nH) vs mesh density</th></tr></thead>
<tbody>{''.join(tb_rows)}</tbody></table>
<p class="muted">Solver: FastHenry 3.0.1 (MIT / FastFieldSolvers 2012 x64 port). Meshing: plane
seg1×seg2 grid plus nhinc×nwinc filaments per trace segment. Convergence = relative L change between
the last two mesh densities; above tolerance the report says so instead of quoting a tight number.</p>"""

    inj_html = ""
    if injection:
        stats = injection["stats"]
        files = injection["files_changed"]
        file_rows = "".join(
            f"<tr><td class='mono'>{e(f['path'])}</td><td>{e(f['action'])}</td><td class='mono'>{e(f.get('detail',''))}</td></tr>"
            for f in files)
        inj_html = f"""
        <h2>4 · QSPICE injection summary</h2>
        <div class="grid3">
          <div class="kpi"><div class="kpi-v">{stats['nets']}</div><div class="kpi-k">nets parasitic-ized</div></div>
          <div class="kpi"><div class="kpi-v">{stats['elements_added']}</div><div class="kpi-k">R/L/C/K elements added</div></div>
          <div class="kpi"><div class="kpi-v">{stats['lines_after']}</div><div class="kpi-k">lines in injected netlist</div></div>
        </div>
        <table>
          <thead><tr><th>File in output project</th><th>Action</th><th>Detail</th></tr></thead>
          <tbody>{file_rows}</tbody>
        </table>"""
    else:
        inj_html = "<h2>4 · Injection</h2><p class='muted'>Analysis only — no project was injected yet.</p>"

    stack_rows = "".join(
        f"<tr><td>{i+1}</td><td class='mono'>{e(l['name'])}</td><td>{e(l['type'])}</td>"
        f"<td>{(l.get('thickness_mm') or 0):.4f}</td>"
        f"<td>{l.get('epsilon_r') if l.get('epsilon_r') else '—'}</td></tr>"
        for i, l in enumerate(analysis["stackup"]))

    notes = []
    for n in nets:
        for note in n.get("notes", []):
            notes.append(f"<li><span class='mono'>{e(n['name'])}</span> — {e(note)}</li>")
    notes_html = f"<ul>{''.join(notes)}</ul>" if notes else "<p class='muted'>No geometry warnings.</p>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PCB Parasitics — Engineering Report — {e(meta.get('design_name','design'))}</title>
<style>
:root{{--accent:{ACCENT};--ink:{INK};--mute:{MUTE};--bg:{BG}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:28px 26px 60px}}
header{{background:linear-gradient(135deg,#0b2239 0%,#0e4a5f 100%);color:#e2f3f7;border-radius:14px;padding:26px 28px;margin-bottom:22px}}
header .eyebrow{{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#7dd3fc}}
h1{{margin:.35em 0 .2em;font-size:26px;line-height:1.25;color:#f0fdff}}
header .meta{{color:#a5c9d4;font-size:12.5px}}
h2{{font-size:17px;margin:28px 0 10px;padding-bottom:6px;border-bottom:2px solid #dbe4ea;color:#0b3b53}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0 6px;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 2px rgba(2,24,40,.08)}}
th{{background:#0b2239;color:#cde9ef;text-align:left;padding:8px 10px;font-size:11px;letter-spacing:.06em;text-transform:uppercase}}
td{{border-top:1px solid #eef2f6;padding:7px 10px}}
tr:nth-child(even) td{{background:#fbfdfe}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}}
.muted{{color:var(--mute)}}
.grid3{{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}}
.kpi{{flex:1;min-width:140px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px}}
.kpi-v{{font-size:24px;font-weight:700;color:var(--accent)}}
.kpi-k{{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.08em}}
.callout{{background:#effaf0;border:1px solid #bbf0d0;border-left:4px solid #16a34a;border-radius:8px;padding:10px 14px;font-size:12.5px;margin:12px 0}}
.warn{{background:#fff8ec;border-color:#fde3b5;border-left-color:#d97706}}
footer{{margin-top:36px;padding-top:14px;border-top:1px solid #e2e8f0;color:var(--mute);font-size:11px}}
ul{{margin:6px 0 0 18px;padding:0}}
td.b,th.b{{background:#f0f9ff}}
th.b{{background:#0c4a6e;color:#bae6fd}}
.chip{{display:inline-block;background:#eef2f7;border-radius:4px;padding:1px 5px;margin:1px 2px;font-size:10.5px}}
.tiny{{font-size:10.5px}}
.ok{{color:#15803d;font-weight:600;font-size:11px}}
.bad{{color:#b91c1c;font-weight:600;font-size:11px}}
</style></head><body><div class="wrap">

<header>
  <div class="eyebrow">PCB Parasitic Engine · QSPICE</div>
  <h1>Parasitic Extraction Report — {e(meta.get('design_name','design'))}</h1>
  <div class="meta">Generated {e(stamp)} · Solver: {e(solver_line)} · Evaluation frequency f₀ = {analysis['f0_hz']/1e6:g} MHz · Source: <span class="mono">{e(meta.get('source_file',''))}</span></div>
</header>

<div class="callout"><b>What this is.</b> This report lists the R/L/C parasitics extracted from your PCB geometry and
shows exactly how they were injected into your QSPICE project. <b>◆</b> marks nets flagged as critical for
power-electronics behaviour (switch node / high dv/dt / gate loop). Values are engineering estimates — see §6 assumptions.</div>

<h2>1 · Stackup</h2>
<table><thead><tr><th>#</th><th>Layer</th><th>Type</th><th>t (mm)</th><th>εr</th></tr></thead>
<tbody>{stack_rows}</tbody></table>
<p class="muted">Laminate height {analysis['laminate_height_mm']:.3f} mm · {analysis['total_nets_in_design']} nets in design · {analysis['zones']} copper zones · {analysis['footprints']} footprints</p>

<h2>2 · Extracted parasitics per net</h2>
<table><thead><tr><th>Net</th><th>ℓ (mm)</th><th>w̄ (mm)</th><th>Ref plane</th>
<th>A: R<sub>AC</sub></th><th>A: L (nH)</th>
{('<th class="b">B: R</th><th class="b">B: L (nH)</th><th class="b">B vs A</th>' if any_b else '')}
<th>C (pF)</th><th>Z₀</th><th>Vias</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>

<h2>3 · Drive-point impedance |Z(f)| — {e(chart_net['name'] if chart_net else '—')}</h2>
{chart}
<p class="muted">Series R–L shunted by trace-to-plane C. For the selected "critical" net.</p>

{tb_html}

{inj_html}

<h2>5 · Geometry & solver warnings</h2>
{notes_html}

<h2>6 · Assumptions & uncertainty</h2>
<ul>
<li>Skin/proximity: R<sub>AC</sub> uses perimeter skin-effect approximation; proximity effect adds 15–40 % when conductors run in tight parallel — use Tier B (PEEC) for sign-off.</li>
<li>Partial inductance formulas assume isolated rectangular filaments; mutual coupling between adjacent nets is only modelled when Tier B provides it.</li>
<li>Trace-to-plane capacitance assumes a solid reference plane directly beneath the trace; voids, splits, or stitching gaps raise L and lower C.</li>
<li>Copper resistivity ρ = 1.72e-8 Ω·m (20 °C); plating & roughness (Hammerstad) not applied — increase R<sub>AC</sub> by ≈10 % for electrodeposited copper.</li>
<li>Reference-plane determination picks the nearest copper layer on either side of a trace, thinnest dielectric gap wins (top/bottom referenced routing handled uniformly). Buried traces between two copper references use the symmetric-stripline formula with b = gap above + trace + gap below.</li>
<li>Tier A targets ±5–10 % for well-behaved geometries. Tier B (FastHenry2) removes the infinite-plane assumption and adds proximity effect; its reported value is the converged mesh result.</li>
<li>Capacitance is always Tier A closed-form in this release: no electrostatic field solver is wired yet (FastCap/FasterCap pending — plan T-304). Treat C as ±10 % and re-check with the fab stackup.</li>
</ul>

<footer>pcb-parasitic-qspice · open-core (MIT) · The PCB parasitics are estimates computed from your geometry;
QSPICE and Linear Technology/Analog Devices are trademarks of their respective owners. Always verify against lab measurements.</footer>
</div></body></html>"""

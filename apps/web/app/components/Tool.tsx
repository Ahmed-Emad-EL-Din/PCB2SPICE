'use client';

import { useEffect, useMemo, useState } from 'react';
import DropZone from '@/app/components/DropZone';
import ImpedanceChart from '@/app/components/ImpedanceChart';
import { analyzePcb, injectProject, ApiError } from '@/lib/api';
import type { AnalyzeResponse, InjectResponse, NetParasitic } from '@/lib/types';
import { fmtF, fmtH, fmtHz, fmtNum, fmtOhm } from '@/lib/format';

type Phase = 'idle' | 'analyzing' | 'ready' | 'injecting' | 'done';

export default function Tool() {
  const [designName, setDesignName] = useState('synchronous-buck');
  const [f0Slider, setF0Slider] = useState(68); // 0..100 → 100 kHz..1 GHz (log)
  const [pcbFile, setPcbFile] = useState<File | null>(null);
  const [projectFile, setProjectFile] = useState<File | null>(null);
  const [cirFile, setCirFile] = useState<File | null>(null);
  const [qschFile, setQschFile] = useState<File | null>(null);
  const [showSingleFile, setShowSingleFile] = useState(false);

  const [phase, setPhase] = useState<Phase>('idle');
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [chartNet, setChartNet] = useState<string | null>(null);
  const [refNode, setRefNode] = useState('0');
  const [tier, setTier] = useState<'A' | 'auto' | 'B'>('auto');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InjectResponse | null>(null);

  // slider maps 0..100 → 1e5 .. 1e9 Hz (log scale)
  const f0HzActual = Math.pow(10, 5 + (f0Slider / 100) * 4);

  const chartTarget: NetParasitic | undefined = useMemo(() => {
    if (!analysis) return undefined;
    const name = chartNet ?? analysis.default_selection[0] ?? analysis.nets[0]?.name;
    return analysis.nets.find((n) => n.name === name);
  }, [analysis, chartNet]);

  const selectedList = useMemo(() => [...selected], [selected]);
  const anyTierB = useMemo(() => analysis?.nets.some((n) => n.tier_b) ?? false, [analysis]);
  const canInject = selectedList.length > 0 && (!!projectFile || !!cirFile || !!qschFile);

  async function runAnalyze() {
    if (!pcbFile) return;
    setError(null);
    setPhase('analyzing');
    setResult(null);
    try {
      const res = await analyzePcb(pcbFile, f0HzActual, tier);
      setAnalysis(res);
      setSelected(new Set(res.default_selection));
      setChartNet(res.default_selection[0] ?? res.nets[0]?.name ?? null);
      setPhase('ready');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Analysis failed — is the worker running?');
      setPhase('idle');
    }
  }

  async function runInject() {
    if (!pcbFile || !canInject) return;
    setError(null);
    setPhase('injecting');
    try {
      const res = await injectProject({
        pcb: pcbFile,
        selection: selectedList,
        project: projectFile,
        cir: cirFile,
        qsch: qschFile,
        refNode,
        designName,
        f0Hz: f0HzActual,
        tier,
      });
      setResult(res);
      setPhase('done');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Injection failed — see the server log.');
      setPhase('ready');
    }
  }

  async function deleteSession() {
    if (!result) return;
    try {
      await fetch(`/api/session/${result.token}`, { method: 'DELETE' });
    } finally {
      setResult(null);
      setPhase('ready');
    }
  }

  function toggleNet(name: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function toggleAll() {
    if (!analysis) return;
    setSelected((prev) =>
      prev.size === analysis.nets.length ? new Set() : new Set(analysis.nets.map((n) => n.name)),
    );
  }

  const stepOf = (p: Phase) =>
    p === 'idle' || p === 'analyzing' ? 1 : p === 'ready' ? 2 : p === 'injecting' ? 3 : 3;
  const currentStep = stepOf(phase);

  return (
    <section className="tool" id="tool" aria-label="Parasitic extraction tool">
      <div className="container">
        <div className="tool-head">
          <div>
            <h2>The workbench</h2>
            <p>Upload your layout, review the extracted R·L·C, inject, download. Your files never leave this machine.</p>
          </div>
          <div className="stepper" aria-hidden="true">
            <span className={`step${currentStep === 1 ? ' active' : ' done'}`}><span className="n">1</span>Upload</span>
            <span className="step-sep" />
            <span className={`step${currentStep === 2 ? ' active' : currentStep > 2 ? ' done' : ''}`}><span className="n">2</span>Extract</span>
            <span className="step-sep" />
            <span className={`step${currentStep === 3 ? ' active' : ''}${phase === 'done' ? ' done' : ''}`}><span className="n">3</span>Inject</span>
          </div>
        </div>

        {/* ── Step 1: upload ─────────────────────────────── */}
        <div className="panel" aria-labelledby="p-upload">
          <h3 id="p-upload" className="panel-title"><span className="tag">Step 1</span> Upload your design &amp; QSPICE project</h3>
          <div className="dropgrid">
            <DropZone
              id="dz-pcb" icon="pcb" required
              title="KiCad layout (.kicad_pcb)"
              hint="PCB Editor file — geometry, stackup and netclasses are read directly."
              accept=".kicad_pcb"
              file={pcbFile}
              onFile={(f) => { setPcbFile(f); setAnalysis(null); setPhase('idle'); }}
            />
            <DropZone
              id="dz-project" icon="zip"
              title="QSPICE project (.zip)"
              hint="Your .cir / .qsch / model library archive — parasitics are written back into it."
              accept=".zip"
              file={projectFile}
              onFile={setProjectFile}
            />
          </div>

          <button className="btn btn-ghost btn-sm" style={{ marginTop: 12 }} onClick={() => setShowSingleFile((v) => !v)} aria-expanded={showSingleFile}>
            {showSingleFile ? '− Hide single-file injection' : '+ No project zip? Inject a single .cir / .qsch instead'}
          </button>
          {showSingleFile && (
            <div className="dropgrid" style={{ marginTop: 12 }}>
              <DropZone id="dz-cir" icon="cir" title="SPICE netlist (.cir)" hint="Node references to target nets are rewritten to add R–L–C." accept=".cir,.sp,.spice,.net,.lib" file={cirFile} onFile={setCirFile} />
              <DropZone id="dz-qsch" icon="qsch" title="QSPICE schematic (.qsch)" hint="Additive-only: .include parasitics.lib appended, geometry untouched." accept=".qsch" file={qschFile} onFile={setQschFile} />
            </div>
          )}

          <div className="form-row">
            <div className="field">
              <label htmlFor="design-name">Design name</label>
              <input id="design-name" type="text" value={designName} onChange={(e) => setDesignName(e.target.value)} placeholder="synchronous-buck" spellCheck={false} />
            </div>
            <div className="field">
              <label htmlFor="f0">Evaluation frequency f₀ — <span className="slider-val">{fmtHz(f0HzActual)}</span></label>
              <input id="f0" type="range" min={0} max={100} step={1} value={f0Slider} onChange={(e) => setF0Slider(Number(e.target.value))} aria-valuetext={fmtHz(f0HzActual)} />
              <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>Resistance is frequency-dependent (skin effect). Power loops: 10–100 MHz. RF: ≤1 GHz.</div>
            </div>

            <div className="field" style={{ marginTop: 14 }}>
              <label htmlFor="tier">Solver tier</label>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }} role="radiogroup" aria-labelledby="tier">
                {([
                  ['auto', 'Auto', 'Closed-form everywhere + field-solve the critical nets'],
                  ['A', 'Tier A', 'Closed-form only — instant, infinite-plane assumption'],
                  ['B', 'Tier B', 'Field-solve every net — finite plane, proximity effect'],
                ] as const).map(([val, label, desc]) => (
                  <button
                    key={val}
                    type="button"
                    role="radio"
                    aria-checked={tier === val}
                    className={`btn btn-sm ${tier === val ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setTier(val)}
                    title={desc}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
                {tier === 'A' && 'Tier A: closed-form only. ±5–10 %, assumes an infinite plane under every trace.'}
                {tier === 'auto' && 'Auto: field-solve the nets flagged ◆ CRITICAL if a FastHenry binary is available; falls back to Tier A with an explicit notice.'}
                {tier === 'B' && 'Tier B: FastHenry2 meshes every net with its real reference plane. Slower (seconds/minutes) but removes the infinite-plane assumption.'}
              </div>
            </div>
          </div>

          {error && <div className="alert alert-error" role="alert">{error}</div>}

          <div style={{ marginTop: 18, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={runAnalyze} disabled={!pcbFile || phase === 'analyzing'}>
              {phase === 'analyzing' ? (<><span className="spin" aria-hidden="true" /> Extracting parasitics…</>) : 'Extract parasitics →'}
            </button>
            {analysis && <button className="btn btn-ghost btn-sm" onClick={runAnalyze}>↻ Re-extract</button>}
            <span className="dim" style={{ fontSize: 12 }}>Anonymous session · 1 h TTL · files stay on this host</span>
          </div>
        </div>

        {/* ── Step 2: results ────────────────────────────── */}
        {analysis && (
          <div className="panel" aria-labelledby="p-extract">
            <h3 id="p-extract" className="panel-title"><span className="tag">Step 2</span> Extracted parasitics <span className="dim" style={{ fontWeight: 400 }}>— {analysis.source_file}</span></h3>

            <div className="summary-grid" role="status">
              <div className="summary-cell"><b>{analysis.laminate_height_mm.toFixed(2)} mm</b><span>laminate height</span></div>
              <div className="summary-cell"><b>{analysis.stackup.filter((l) => l.type === 'copper').length}</b><span>copper layers</span></div>
              <div className="summary-cell"><b>{analysis.nets.length}</b><span>extractable nets</span></div>
              <div className="summary-cell"><b>{fmtHz(analysis.f0_hz)}</b><span>evaluation f₀</span></div>
            </div>

            {analysis.warnings.map((w) => <div className="alert alert-warn" key={w}>{w}</div>)}

            {analysis.field?.fallback_reason && (
              <div className="alert alert-warn" role="status">
                <b>Tier B unavailable —</b> {analysis.field.fallback_reason}
              </div>
            )}
            {analysis.field?.solved && analysis.field.solved.length > 0 && (
              <div className="alert alert-ok" role="status">
                <b>Field solve complete</b> — {analysis.field.solved.length} net
                {analysis.field.solved.length === 1 ? '' : 's'} solved with FastHenry2
                ({analysis.field.solved.join(', ')}). Tier A and Tier B values are shown side by side;
                injection uses Tier B.
              </div>
            )}
            {analysis.field?.skipped && analysis.field.skipped.length > 0 && (
              <div className="alert alert-warn" role="status">
                {analysis.field.skipped.map((sk) => `${sk.net}: ${sk.reason}`).join(' · ')}
              </div>
            )}

            <div className={`split${anyTierB ? ' split-wide-table' : ''} tierb-active`}>
              <div>
                <div className="tablewrap">
                  <table className={`nets${anyTierB ? ' has-tierb' : ''}`}>
                    <thead>
                      <tr>
                        <th><input type="checkbox" className="row-check" aria-label="Select all nets" checked={selected.size === analysis.nets.length && analysis.nets.length > 0} onChange={toggleAll} /></th>
                        <th>Net</th><th>ℓ (mm)</th><th className="col-opt">w̄ (mm)</th><th>Ref plane</th>
{anyTierB ? (
  <>
    <th title="Tier A closed-form">A · R<sub>AC</sub></th><th title="Tier A closed-form">A · L</th>
    <th className="th-b" title="Tier B FastHenry2 field solve">B · R</th>
    <th className="th-b" title="Tier B FastHenry2 field solve">B · L</th>
    <th className="th-b" title="Tier B vs Tier A">Δ</th>
  </>
) : (
  <><th>R<sub>AC</sub></th><th>L</th></>
)}
<th>C</th><th>Z₀</th><th className="col-opt">Vias</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analysis.nets.map((n) => (
                        <tr key={n.name} className={selected.has(n.name) ? 'selected' : ''} onClick={() => toggleNet(n.name)} aria-selected={selected.has(n.name)}>
                          <td><input type="checkbox" className="row-check" checked={selected.has(n.name)} onChange={() => toggleNet(n.name)} onClick={(e) => e.stopPropagation()} aria-label={`Select net ${n.name}`} /></td>
                          <td className="mono">{n.name}{n.critical && <span className="crit-badge" title={n.critical_reason ?? 'Power-electronics critical net'}>◆ CRITICAL</span>}</td>
                          <td className="mono">{fmtNum(n.total_length_mm, 1)}</td>
                          <td className="mono col-opt">{fmtNum(n.avg_width_mm, 2)}</td>
                          <td className="mono">{n.ref_plane ?? '—'}</td>
                          <td className="mono">{fmtOhm(n.r_ac)}</td>
                          <td className="mono">{fmtH(n.l_h)}</td>
                          {anyTierB && (
                            <>
                              <td className="mono cell-b">{n.tier_b ? fmtOhm(n.tier_b.r_ohm) : '—'}</td>
                              <td className="mono cell-b">{n.tier_b ? fmtH(n.tier_b.l_h) : '—'}</td>
                              <td className="mono cell-b" title={n.tier_b ? `${n.tier_b.convergence.converged ? 'converged' : 'NOT converged'} · ${(n.tier_b.convergence.l_drift * 100).toFixed(1)} % mesh drift · ${n.tier_b.filaments.toLocaleString()} filaments` : undefined}>
                                {n.tier_b?.delta_vs_tier_a.l_pct != null
                                  ? `${n.tier_b.delta_vs_tier_a.l_pct > 0 ? '+' : ''}${n.tier_b.delta_vs_tier_a.l_pct.toFixed(1)}%`
                                  : '—'}
                                {n.tier_b && !n.tier_b.convergence.converged && <span title="mesh not converged" aria-label="not converged"> ⚠</span>}
                              </td>
                            </>
                          )}
                          <td className="mono">{fmtF(n.c_f)}</td>
                          <td className="mono">{n.z0 ? `${n.z0.toFixed(1)} Ω` : '—'}</td>
                          <td className="mono col-opt">{n.vias}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {analysis.nets.some((n) => n.critical) && (
                  <p className="crit-note">◆ Switching-node &amp; gate-loop nets are flagged for you. Keep them selected — they dominate ringing and EMI.</p>
                )}
                {anyTierB && (
                  <div className="tierb-note">
                    <b>Why B ≠ A.</b> Tier A assumes an infinite copper plane directly under every
                    trace. Tier B meshes the real finite plane, every segment and via, and solves the
                    magneto-quasistatic field. A larger B value means the return current cannot stay
                    under the trace — that is what your copper actually does. Injection uses the{' '}
                    <b>B</b> values; C stays closed-form.
                    {analysis.nets.filter((n) => n.tier_b).map((n) => (
                      <span key={n.name} className="tierb-chip mono">
                        {n.name}: {n.tier_b!.convergence.converged ? '✓' : '⚠'} {n.tier_b!.filaments.toLocaleString()} fil ·{' '}
                        {(n.tier_b!.convergence.l_drift * 100).toFixed(1)}% drift
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="chart-box">
                  <div className="chart-title">
                    <span>Drive-point |Z(f)|</span>
                    <span className="mono">{chartTarget ? `net ${chartTarget.name}` : '—'}</span>
                  </div>
                  {chartTarget && <ImpedanceChart f={chartTarget.impedance_sweep.f_hz} z={chartTarget.impedance_sweep.z_ohm} />}
                  <div className="dim" style={{ fontSize: 11, marginTop: 8 }}>R–L with trace-to-plane shunt C · click any row to chart that net</div>
                </div>
                <div style={{ marginTop: 12 }}>
                  <div className="chart-title" style={{ marginBottom: 6 }}>Stackup (top → bottom)</div>
                  <div className="tablewrap">
                    <table className="nets compact" style={{ minWidth: 0 }}>
                      <tbody>
                        {analysis.stackup.map((l, i) => (
                          <tr key={i} style={{ cursor: 'default' }}>
                            <td className="mono dim">{i + 1}</td>
                            <td className="mono">{l.name}</td>
                            <td className="dim">{l.type}</td>
                            <td className="mono">{l.thickness_mm ? `${l.thickness_mm.toFixed(3)} mm` : '—'}</td>
                            <td className="mono">{l.epsilon_r ?? ''}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Step 3: inject ─────────────────────────────── */}
        {analysis && phase !== 'done' && (
          <div className="panel" aria-labelledby="p-inject">
            <h3 id="p-inject" className="panel-title"><span className="tag">Step 3</span> Inject into your QSPICE project</h3>
            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'end' }}>
              <div className="field" style={{ maxWidth: 220 }}>
                <label htmlFor="refnode">Shunt reference node</label>
                <input id="refnode" type="text" value={refNode} onChange={(e) => setRefNode(e.target.value)} spellCheck={false} autoComplete="off" />
              </div>
              <div className="dim" style={{ fontSize: 12.5, maxWidth: 520 }}>
                Capacitor parasitics are returned to this node (usually <span className="mono">0</span>, the SPICE ground).
                Series R–L and the <span className="mono">.cir</span> node rewrite apply to: <span className="mono">{selectedList.join(', ') || 'no nets selected'}</span>
              </div>
            </div>
            <div style={{ marginTop: 16, display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-primary" onClick={runInject} disabled={!canInject || phase === 'injecting'}>
                {phase === 'injecting' ? (<><span className="spin" aria-hidden="true" /> Writing parasitics…</>) : 'Build parasitic-injected project →'}
              </button>
              {!canInject && (
                <span className="alert alert-warn" style={{ margin: 0, padding: '8px 12px' }}>
                  {selectedList.length === 0 ? 'Select at least one net above.' : 'Add a project .zip (or a .cir / .qsch) in Step 1 to inject into.'}
                </span>
              )}
            </div>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
          </div>
        )}

        {/* ── Done ───────────────────────────────────────── */}
        {result && phase === 'done' && (
          <div className="panel" aria-labelledby="p-done">
            <h3 id="p-done" className="panel-title"><span className="tag">Done</span> Your parasitic-aware QSPICE project</h3>
            <div className="ok-banner">
              <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true"><circle cx="17" cy="17" r="16" stroke="#34d399" strokeWidth="1.6" /><path d="M11 17.5l4 4 8-9" stroke="#34d399" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <div>
                <b>Parasitics are in the files.</b>
                <div className="dim" style={{ fontSize: 13 }}>QSPICE will now simulate the trace you actually laid out — ringing, EMI drivers and gate-loop inductance included.</div>
              </div>
            </div>
            <div className="kpi-row">
              <div className="kpi"><b>{result.stats.nets}</b><span>nets injected</span></div>
              <div className="kpi"><b>{result.stats.elements_added}</b><span>R·L·C·K elements</span></div>
              <div className="kpi"><b>{result.files_changed.filter((f) => f.action !== 'skipped').length}</b><span>files written</span></div>
              <div className="kpi"><b>{result.stats.lines_after || '—'}</b><span>netlist lines</span></div>
            </div>
            <div className="tablewrap">
              <table className="files-table">
                <thead><tr><th>File in package</th><th>Action</th><th>Details</th></tr></thead>
                <tbody>
                  {result.files_changed.map((f, i) => (
                    <tr key={i}>
                      <td className="mono">{f.path}</td>
                      <td><span className={`pill pill-${f.action}`}>{f.action}</span></td>
                      <td className="dim">{f.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="download-row">
              <a className="btn btn-primary" href={result.download} download>↓ Download parasitic-injected .zip</a>
              <a className="btn btn-ghost" href={result.report} target="_blank" rel="noreferrer">Open engineering report ↗</a>
              <button className="btn btn-ghost btn-sm" onClick={deleteSession}>Delete session data</button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

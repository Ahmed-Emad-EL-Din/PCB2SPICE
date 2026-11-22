import Tool from '@/app/components/Tool';

const kvRows: Array<[string, string]> = [
  ['net SW · length', '45.0 mm'],
  ['R(AC) @ 50 MHz', '79.8 mΩ'],
  ['L (incl. via)', '13.2 nH'],
  ['C trace→plane', '7.5 pF'],
  ['Z₀', '39.3 Ω'],
  ['.cir transform', 'R₁ vin sw → sw__PAR'],
  ['.qsch', '+ .include parasitics.lib'],
];

export default function Home() {
  return (
    <>
      {/* ── top bar ─────────────────────────────────────── */}
      <header className="topbar">
        <div className="container topbar-inner">
          <a className="brand" href="#" aria-label="PCB Parasitic Engine — home">
            <svg className="brand-mark" width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
              <rect x="1.5" y="1.5" width="31" height="31" rx="8" stroke="#2dd4bf" strokeWidth="1.6" />
              <path d="M6 20.5h4.2c1.2 0 1.2-7 2.9-7s1.7 7 3.4 7 1.7-7 3.4-7 1.7 7 3.4-7 1.7 7 3.4 7H28" stroke="#5eead4" strokeWidth="1.7" strokeLinecap="round" />
              <circle cx="6" cy="20.5" r="1.5" fill="#38bdf8" />
              <circle cx="28" cy="20.5" r="1.5" fill="#38bdf8" />
            </svg>
            <span className="brand-name">PCB <em>Parasitic</em> Engine<span className="brand-sub">for QSPICE</span></span>
          </a>
          <nav className="topnav" aria-label="Section">
            <a href="#how">How it works</a>
            <a href="#tiers">Accuracy</a>
            <a href="#faq">FAQ</a>
            <span className="tier-pill"><span className="dot" />Tier A · live</span>
          </nav>
        </div>
      </header>

      {/* ── hero ────────────────────────────────────────── */}
      <section className="hero">
        <div className="container hero-grid">
          <div>
            <span className="eyebrow"><span className="pulse" />KiCad → QSPICE · closed loop</span>
            <h1 className="hero-title">Simulate the <span className="grad">layout you actually built.</span></h1>
            <p className="hero-sub">
              Upload your <span className="mono">.kicad_pcb</span> and QSPICE project. We extract trace
              resistance, partial inductance (with reference planes and vias) and trace-to-plane
              capacitance — then inject them straight into your <span className="mono">.cir</span> and
              <span className="mono"> .qsch</span> files, with a full engineering report.
            </p>
            <div className="hero-ctas">
              <a className="btn btn-primary" href="#tool">Extract my parasitics <span aria-hidden="true">→</span></a>
              <a className="btn btn-ghost" href="#how">How it works</a>
            </div>
            <div className="statstrip" aria-label="Key numbers">
              <div className="stat"><b>R·L·C</b><span>per routed net, stackup-aware</span></div>
              <div className="stat"><b>&lt; 1 s</b><span>Tier A closed-form solve</span></div>
              <div className="stat"><b>2 paths</b><span>.cir rewrite &amp; additive .qsch</span></div>
              <div className="stat"><b>0 B</b><span>uploaded off-host — self-hostable</span></div>
            </div>
          </div>

          <aside className="hero-card" aria-label="Example extraction session">
            <div className="hero-card-head">
              <span className="hero-card-title">Live extraction — sync_buck.kicad_pcb</span>
              <span className="live-dot"><i />worked example</span>
            </div>
            {kvRows.map(([k, v]) => (
              <div className="kv" key={k}><span className="k">{k}</span><span className="v">{v}</span></div>
            ))}
            <div className="hero-card-foot">Example from the built-in probe board. Numbers update from your own layout in Step 2.</div>
          </aside>
        </div>
      </section>

      {/* ── the tool ────────────────────────────────────── */}
      <Tool />

      {/* ── how it works ────────────────────────────────── */}
      <section className="section" id="how">
        <div className="container">
          <h3>How it works</h3>
          <p className="lead">Three steps, no netlist hand-editing, no schematic symbol surgery. Everything downstream of “Extract” is written into files QSPICE already understands.</p>
          <div className="cards3">
            <div className="info-card">
              <div className="info-icon"><svg width="22" height="22" viewBox="0 0 22 22" fill="none"><rect x="2" y="4" width="18" height="14" rx="2" stroke="#2dd4bf" strokeWidth="1.5" /><circle cx="7" cy="9" r="1.3" stroke="#38bdf8" /><circle cx="15" cy="13" r="1.3" stroke="#38bdf8" /><path d="M7 10.5v2a2 2 0 0 0 2 2h6" stroke="#2dd4bf" strokeWidth="1.5" /></svg></div>
              <h4>1 · Read the geometry</h4>
              <p>kiutils parses your <span className="mono">.kicad_pcb</span>: copper segments, vias, widths, layers and the stackup (foil thickness, prepreg/core ε<sub>r</sub>). Zones are detected and reported. KiCad 6/7/8 files included.</p>
            </div>
            <div className="info-card">
              <div className="info-icon"><svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M3 15c2 0 2-8 4-8s2 8 4 8 2-8 4-8 2 8 4-8" stroke="#2dd4bf" strokeWidth="1.5" strokeLinecap="round" /><path d="M3 19h16" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" /></svg></div>
              <h4>2 · Solve the parasitics</h4>
              <p>Closed-form kernel: Hammerstad–Jensen microstrip / IPC-2141A stripline, Grover partial inductance, via barrel inductance and skin-effect resistance vs. your f₀. Provenance travels with every number.</p>
            </div>
            <div className="info-card">
              <div className="info-icon"><svg width="22" height="22" viewBox="0 0 22 22" fill="none"><path d="M6 3v6a5 5 0 0 0 5 5v5" stroke="#2dd4bf" strokeWidth="1.5" strokeLinecap="round" /><path d="M16 3v6a5 5 0 0 1-5 5" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" /><circle cx="6" cy="3" r="1.4" fill="#2dd4bf" /><circle cx="16" cy="3" r="1.4" fill="#38bdf8" /></svg></div>
              <h4>3 · Inject &amp; download</h4>
              <p><span className="mono">.cir</span>: whole-net rewrite — every consumer of the net now hangs off the R–L ladder, shunt C returned to your reference node. <span className="mono">.qsch</span>: purely additive — <span className="mono">.include parasitics.lib</span> plus a provenance comment block. Geometry is never touched.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── accuracy tiers ──────────────────────────────── */}
      <section className="section" id="tiers">
        <div className="container">
          <h3>Accuracy, stated honestly</h3>
          <p className="lead">Two solvers are live: a closed-form kernel for instant estimates and a real PEEC field solver for sign-off numbers. Pick per job; the report always names the method used on every net.</p>
          <div style={{ overflowX: 'auto' }}>
            <table className="tier-table">
              <thead><tr><th>Tier</th><th>Method</th><th>Typical error</th><th>Cost</th><th>Status</th></tr></thead>
              <tbody>
                <tr className="current"><td><b>A — closed-form</b><span className="pill pill-additive-inject">live now</span></td><td>Hammerstad–Jensen, IPC-2141A, Grover, skin effect</td><td>±5–10 % on well-behaved geometries</td><td>&lt; 1 s, runs anywhere</td><td>Available — this release</td></tr>
                <tr className="current"><td><b>B — PEEC field solve</b><span className="pill pill-additive-inject">live now</span></td><td>FastHenry2 mesh solve for L/R — finite reference plane, proximity effect, via loops, current crowding</td><td>±2–5 %; convergence reported per net</td><td>0.1–3 s per net (1–10 k filaments)</td><td>Available — L/R. Capacitance still closed-form</td></tr>
                <tr><td><b>C — full-wave</b></td><td>openEMS FDTD cross-check on critical loops</td><td>reference-grade</td><td>minutes–hours</td><td>Research track</td></tr>
              </tbody>
            </table>
          </div>
          <div className="alert alert-info" style={{ marginTop: 14 }}>
            <b>What Tier A doesn’t claim:</b> the closed form puts an infinite copper plane under every
            trace. Tier B meshes the plane you actually have — which is why a switching node can read
            +46 % higher loop inductance on a finite plane with one return via. Both numbers are shown,
            the mesh-convergence drift is printed next to each one, and injection always uses Tier B when
            it ran.
          </div>
        </div>
      </section>

      {/* ── FAQ ─────────────────────────────────────────── */}
      <section className="section" id="faq">
        <div className="container">
          <h3>Questions power engineers actually ask</h3>
          <div className="faq-list" style={{ marginTop: 18 }}>
            <details className="faq-item"><summary>Does it rewrite my QSPICE schematic?</summary><p>Never in place. <span className="mono">.qsch</span> files receive purely additive text records appended before the root close: an <span className="mono">.include parasitics.lib</span> directive and a commented provenance block — no symbol, wire or geometry record is modified. <span className="mono">.cir</span> netlists are rewritten node-by-node inside a <em>new</em> package; the archive you uploaded is never mutated.</p></details>
            <details className="faq-item"><summary>Which nets get parasitics?</summary><p>Every signal net in your stackup-aware analysis is listed. Ground/reference nets (0, GND, PGND…) are excluded from selection by default but visible. Nets matching switching-node / gate-drive / bulk-rail patterns are auto-flagged ◆ CRITICAL and pre-selected — you remain in charge.</p></details>
            <details className="faq-item"><summary>Where do my files go?</summary><p>Nowhere. Extraction runs in this session’s worker; results live in an anonymous 1-hour TTL directory on the host and can be wiped with one button. For production tape-out, self-host the open-core engine (MIT) inside your network.</p></details>
            <details className="faq-item"><summary>Is this compatible with ngspice / LTspice syntax?</summary><p>The injected syntax (R, L, C, K, .include, .end) is plain SPICE. ngspice and QSPICE both consume it. The .qsch container is QSPICE-specific. An ngspice smoke-test harness ships with the Tier B worker (plan T-404).</p></details>
            <details className="faq-item"><summary>My board has copper zones — do they count?</summary><p>Zones are detected and reported in the analysis panel, but the parasitic solver currently reads routed segments and vias. Zone-aware extraction (plane cavities, current spreading) is on the roadmap (plan T-102). Treat plane-heavy designs as Tier B candidates.</p></details>
          </div>
        </div>
      </section>

      {/* ── footer ──────────────────────────────────────── */}
      <footer className="site">
        <div className="container">
          <div>
            <b style={{ color: 'var(--text-dim)' }}>PCB Parasitic Engine for QSPICE</b><br />
            Open-core · MIT engine · parasitics are engineering estimates — verify critical loops by lab measurement.
          </div>
          <div>
            QSPICE is a trademark of Analog Devices. Not affiliated.<br />
            KiCad is a trademark of the KiCad project.
          </div>
        </div>
      </footer>
    </>
  );
}

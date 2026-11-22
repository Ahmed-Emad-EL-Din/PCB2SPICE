'use client';

import { useMemo } from 'react';

/**
 * Log-scale |Z(f)| plot rendered as inline SVG (no chart library, no network).
 */
export default function ImpedanceChart({ f, z }: { f: number[]; z: number[] }) {
  const W = 560, H = 210, padL = 44, padR = 12, padT = 14, padB = 30;

  const model = useMemo(() => {
    if (!f.length) return null;
    const lf = f.map((v) => Math.log10(v));
    const lz = z.map((v) => Math.log10(Math.max(v, 1e-6)));
    const x0 = Math.min(...lf), x1 = Math.max(...lf);
    const y0 = Math.min(...lz), y1 = Math.max(...lz);
    const iw = W - padL - padR, ih = H - padT - padB;
    const X = (i: number) => padL + ((lf[i] - x0) / Math.max(x1 - x0, 1e-9)) * iw;
    const Y = (i: number) => padT + (1 - (lz[i] - y0) / Math.max(y1 - y0, 1e-9)) * ih;
    const pts = f.map((_, i) => `${X(i).toFixed(1)},${Y(i).toFixed(1)}`).join(' ');
    const decades: { xp: number; label: string }[] = [];
    for (let g = Math.ceil(x0); g <= x1 + 1e-9; g++) {
      decades.push({ xp: padL + ((g - x0) / Math.max(x1 - x0, 1e-9)) * iw, label: `1e${g} Hz` });
    }
    return { pts, decades, padT, ih };
  }, [f, z]);

  if (!model) return <div className="chart-box dim">No sweep data.</div>;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Drive-point impedance magnitude versus frequency">
      <rect x="0" y="0" width={W} height={H} rx="10" fill="#0a1a28" stroke="#16304a" />
      {model.decades.map((d) => (
        <g key={d.label}>
          <line x1={d.xp} y1={padT} x2={d.xp} y2={H - padB} stroke="#16304a" strokeDasharray="3 4" />
          <text x={d.xp} y={H - 12} fontSize="9" fill="#6b8798" textAnchor="middle" fontFamily="ui-monospace,Menlo,monospace">
            {d.label}
          </text>
        </g>
      ))}
      <polyline points={model.pts} fill="none" stroke="#2dd4bf" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      <text x={padL - 8} y={padT + 6} fontSize="9" fill="#6b8798" textAnchor="end" fontFamily="ui-monospace,Menlo,monospace">Ω</text>
    </svg>
  );
}

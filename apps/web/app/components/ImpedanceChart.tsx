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
    const yTicks: { yp: number; label: string }[] = [];
    const yMinDec = Math.floor(y0);
    const yMaxDec = Math.ceil(y1);
    const fmtDec = (exp: number) => {
      if (exp === 0) return '1 Ω';
      if (exp === 3) return '1 kΩ';
      if (exp === -3) return '1 mΩ';
      return `1e${exp}`;
    };
    for (let g = yMinDec; g <= yMaxDec; g++) {
      const yp = padT + (1 - (g - y0) / Math.max(y1 - y0, 1e-9)) * ih;
      if (yp >= padT - 2 && yp <= H - padB + 2) {
        yTicks.push({ yp, label: fmtDec(g) });
      }
    }
    return { pts, decades, yTicks, padT, ih };
  }, [f, z]);

  if (!model) return <div className="chart-box dim">No sweep data.</div>;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Drive-point impedance magnitude versus frequency">
      <rect x="0" y="0" width={W} height={H} rx="10" fill="#0a1a28" stroke="#16304a" />
      {model.yTicks.map((t) => (
        <g key={t.label}>
          <line x1={padL} y1={t.yp} x2={W - padR} y2={t.yp} stroke="#16304a" strokeDasharray="3 4" />
          <text x={padL - 6} y={t.yp + 3} fontSize="8.5" fill="#6b8798" textAnchor="end" fontFamily="ui-monospace,Menlo,monospace">
            {t.label}
          </text>
        </g>
      ))}
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

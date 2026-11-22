/** Engineering SI formatting helpers. */
export function fmtHz(hz: number): string {
  if (hz >= 1e9) return `${(hz / 1e9).toFixed(2)} GHz`;
  if (hz >= 1e6) return `${(hz / 1e6).toFixed(hz % 1e6 === 0 ? 0 : 2)} MHz`;
  if (hz >= 1e3) return `${(hz / 1e3).toFixed(1)} kHz`;
  return `${hz.toFixed(0)} Hz`;
}

export function fmtOhm(ohm: number): string {
  if (ohm >= 1) return `${ohm.toFixed(3)} Ω`;
  if (ohm >= 1e-3) return `${(ohm * 1e3).toFixed(2)} mΩ`;
  return `${(ohm * 1e6).toFixed(2)} µΩ`;
}

export function fmtH(l: number): string {
  if (l >= 1e-6) return `${(l * 1e6).toFixed(3)} µH`;
  if (l >= 1e-9) return `${(l * 1e9).toFixed(3)} nH`;
  return `${(l * 1e12).toFixed(1)} pH`;
}

export function fmtF(c: number): string {
  if (c >= 1e-9) return `${(c * 1e9).toFixed(3)} nF`;
  if (c >= 1e-12) return `${(c * 1e12).toFixed(3)} pF`;
  return `${(c * 1e15).toFixed(1)} fF`;
}

export function fmtNum(v: number, digits = 3): string {
  return v.toFixed(digits);
}

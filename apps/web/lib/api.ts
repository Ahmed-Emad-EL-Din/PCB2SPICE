import type { AnalyzeResponse, InjectResponse } from '@/lib/types';

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function extractError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ');
    return JSON.stringify(body);
  } catch {
    return `Request failed with status ${res.status}`;
  }
}

export async function analyzePcb(
  pcb: File,
  f0Hz: number,
  tier: 'A' | 'auto' | 'B' = 'auto',
  fieldNets?: string[],
): Promise<AnalyzeResponse> {
  const fd = new FormData();
  fd.append('pcb', pcb);
  fd.append('f0', String(f0Hz));
  fd.append('tier', tier);
  if (fieldNets?.length) fd.append('field_nets', fieldNets.join(','));
  const res = await fetch('/api/analyze', { method: 'POST', body: fd });
  if (!res.ok) throw new ApiError(await extractError(res), res.status);
  return res.json();
}

export type InjectArgs = {
  pcb: File;
  selection: string[];
  project?: File | null;
  cir?: File | null;
  qsch?: File | null;
  refNode: string;
  designName: string;
  f0Hz: number;
  tier?: 'A' | 'auto' | 'B';
};

export async function injectProject(args: InjectArgs): Promise<InjectResponse> {
  const fd = new FormData();
  fd.append('pcb', args.pcb);
  fd.append('selection', JSON.stringify({ nets: args.selection }));
  fd.append('ref_node', args.refNode);
  fd.append('design_name', args.designName);
  fd.append('f0', String(args.f0Hz));
  fd.append('tier', args.tier ?? 'auto');
  if (args.project) fd.append('project', args.project);
  if (args.cir) fd.append('cir_file', args.cir);
  if (args.qsch) fd.append('qsch_file', args.qsch);
  const res = await fetch('/api/inject', { method: 'POST', body: fd });
  if (!res.ok) throw new ApiError(await extractError(res), res.status);
  return res.json();
}

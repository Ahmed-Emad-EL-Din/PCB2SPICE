export type StackupLayer = {
  type: 'copper' | 'dielectric';
  name: string;
  thickness_mm: number | null;
  epsilon_r?: number | null;
  material?: string | null;
};

export type TierBResult = {
  r_ohm: number;
  l_h: number;
  f_hz: number;
  solver: string;
  filaments: number;
  meshes: number;
  runtime_s: number;
  convergence: {
    points: { seg_density: number; l_h: number; r_ohm: number; filaments: number; runtime_s: number }[];
    l_drift: number;
    converged: boolean;
    tol: number;
    note: string;
  };
  geometry: Record<string, unknown>;
  warnings: string[];
  delta_vs_tier_a: { r_pct: number | null; l_pct: number | null };
};

export type SolverInfo = {
  tier_b_available: boolean;
  fasthenry: string | null;
  fasthenry_version: string | null;
  tier_c_available: boolean;
  tier_c_note: string;
};

export type NetParasitic = {
  name: string;
  total_length_mm: number;
  avg_width_mm: number;
  ref_plane: string | null;
  height_mm: number | null;
  r_dc: number;
  r_ac: number;
  l_h: number;
  c_f: number;
  z0: number | null;
  er_eff: number | null;
  vias: number;
  l_via_total_h: number;
  critical: boolean;
  critical_reason: string | null;
  segments: number;
  method: string;
  uncertainty: string;
  notes: string[];
  impedance_sweep: { f_hz: number[]; z_ohm: number[] };
  /** Present when a Tier B field solve was run for this net. */
  tier_b?: TierBResult;
};

export type AnalyzeResponse = {
  ok: boolean;
  engine_version: string;
  f0_hz: number;
  tier_requested?: 'A' | 'AUTO' | 'B' | string;
  tier_effective?: 'A' | 'B';
  field?: {
    requested_tier: string;
    solver: SolverInfo;
    solved: string[];
    skipped: { net: string; reason: string }[];
    fallback_reason: string | null;
  };
  stackup: StackupLayer[];
  laminate_height_mm: number;
  total_nets_in_design: number;
  footprints: number;
  zones: number;
  nets: NetParasitic[];
  default_selection: string[];
  critical_nets: string[];
  warnings: string[];
  source_file: string;
};

export type FileChange = { path: string; action: 'transformed' | 'additive-inject' | 'generated' | 'skipped' | string; detail?: string };

export type InjectResponse = {
  token: string;
  download: string;
  report: string;
  stats: {
    nets: number; elements_added: number; lines_before: number; lines_after: number;
    r_added: number; l_added: number; c_added: number; k_added: number;
  };
  files_changed: FileChange[];
  nets: string[];
};

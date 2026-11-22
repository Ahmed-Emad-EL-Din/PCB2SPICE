'use client';

import { useRef, useState } from 'react';

type DropZoneProps = {
  id: string;
  title: string;
  hint: string;
  accept: string;
  required?: boolean;
  file: File | null;
  onFile: (f: File | null) => void;
  icon: 'pcb' | 'zip' | 'cir' | 'qsch';
};

function Icon({ kind }: { kind: DropZoneProps['icon'] }) {
  const common = { width: 40, height: 40, viewBox: '0 0 40 40', fill: 'none' } as const;
  switch (kind) {
    case 'pcb':
      return (
        <svg {...common} className="dz-icon">
          <rect x="4" y="6" width="32" height="28" rx="3.5" stroke="#2dd4bf" strokeWidth="1.6" />
          <circle cx="12" cy="15" r="2.1" stroke="#38bdf8" strokeWidth="1.4" />
          <circle cx="28" cy="25" r="2.1" stroke="#38bdf8" strokeWidth="1.4" />
          <path d="M12 17.5v6a4 4 0 0 0 4 4h6" stroke="#2dd4bf" strokeWidth="1.6" />
          <path d="M28 22.5v-4a4 4 0 0 0-4-4h-4" stroke="#f59e0b" strokeWidth="1.6" />
        </svg>
      );
    case 'zip':
      return (
        <svg {...common} className="dz-icon">
          <path d="M12 4h11l8 8v24a2 2 0 0 1-2 2H12a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" stroke="#38bdf8" strokeWidth="1.6" strokeLinejoin="round" />
          <path d="M23 4v8h8" stroke="#38bdf8" strokeWidth="1.6" strokeLinejoin="round" />
          <path d="M18 12h4M18 17h4M18 22h4M20 27v3.5" stroke="#2dd4bf" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case 'cir':
      return (
        <svg {...common} className="dz-icon">
          <path d="M6 12h10M24 12h10M6 28h10M24 28h10" stroke="#9db8c8" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M16 8l4 4-4 4M24 24l4 4-4 4" stroke="#2dd4bf" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" transform="translate(-4 0)" />
        </svg>
      );
    case 'qsch':
      return (
        <svg {...common} className="dz-icon">
          <rect x="5" y="5" width="30" height="30" rx="3" stroke="#a78bfa" strokeWidth="1.6" />
          <path d="M12 26c2.5 0 2.5-12 5-12s2.5 12 5 12 2.5-12 5-12" stroke="#a78bfa" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
  }
}

export default function DropZone({ id, title, hint, accept, required, file, onFile, icon }: DropZoneProps) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <label
      htmlFor={id}
      className={`dropzone${drag ? ' drag' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0] ?? null;
        if (f) onFile(f);
      }}
    >
      <span className={required ? 'dz-req' : 'dz-optional'}>{required ? 'required' : 'optional'}</span>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={accept}
        aria-label={title}
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      <Icon kind={icon} />
      <h4>{title}</h4>
      <p>{hint}</p>
      {file ? (
        <div className="dz-file">✓ {file.name} <span className="dim">({(file.size / 1024 / 1024).toFixed(2)} MB)</span></div>
      ) : null}
    </label>
  );
}

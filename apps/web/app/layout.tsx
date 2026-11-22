import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'PCB Parasitic Engine for QSPICE — extract R·L·C from your layout',
  description:
    'Upload a KiCad PCB + QSPICE project. Extract trace resistance, partial inductance, via inductance and trace-to-plane capacitance — inject them into .cir and .qsch files and download an engineering report.',
  keywords: ['PCB', 'parasitics', 'QSPICE', 'KiCad', 'extraction', 'power electronics', 'PEEC', 'skin effect'],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

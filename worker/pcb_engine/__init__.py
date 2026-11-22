"""pcb_engine — PCB parasitic extraction & QSPICE project injection.

Layers:
    parasitics.py  closed-form (Tier A) R / L / C kernel (documented formulas)
    kicad.py       .kicad_pcb geometry ingestion (via kiutils)
    cir.py         SPICE netlist parse + targeted net transformation
    qsch.py        QSPICE .qsch parse / additive injection (verified byte format)
    report.py      HTML engineering report generator
    pipeline.py    end-to-end orchestration (zip in -> zip out + report)
"""

__version__ = "0.1.0"

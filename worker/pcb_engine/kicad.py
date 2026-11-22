"""KiCad `.kicad_pcb` ingestion (via kiutils) → net geometry model.

Produces the structure the Tier A kernel consumes:
    {
      "nets": [ {"net": "SW", "number": 2, "segments": [{length_m, width_m, layer, x1,y1,x2,y2}],
                 "vias": 1, "via_drill_mm": 0.3, "via_span_mm": 1.6} ],
      "stackup": [ {"type": "copper"|"dielectric", "name": "F.Cu",
                    "thickness_mm": .., "epsilon_r": ..} ],
    }
Also returns list of *every* copper layer name found and a board bounding box
(useful sanity signals for the UI). Zones are noted but not yet integrated
into the kernel (tracked in plan T-102).
"""
from __future__ import annotations

import math
from typing import Any

from kiutils.board import Board
from kiutils.items.brditems import Segment, Via


def _segment_length(seg: Segment) -> float:
    dx = (seg.end.X or 0.0) - (seg.start.X or 0.0)
    dy = (seg.end.Y or 0.0) - (seg.start.Y or 0.0)
    return math.hypot(dx, dy) * 1e-3  # mm → m


def _net_name_by_number(board: Board) -> dict[int, str]:
    out: dict[int, str] = {}
    for n in board.nets:
        out[int(n.number)] = n.name
    return out


def _stackup(board: Board) -> list[dict[str, Any]]:
    setup = getattr(board, "setup", None)
    su = getattr(setup, "stackup", None) if setup else None
    layers: list[dict[str, Any]] = []
    if su and getattr(su, "layers", None):
        for ly in su.layers:
            layers.append({
                "type": "copper" if ly.type == "copper" else "dielectric",
                "name": ly.name,
                "thickness_mm": getattr(ly, "thickness", None),
                "epsilon_r": getattr(ly, "epsilonR", None),
                "material": getattr(ly, "material", None),
            })
    if not layers:  # fall back: guess copper layers from board.layers, assume 1.6 mm FR-4
        copper = [l.name for l in getattr(board, "layers", [])
                  if getattr(l, "type", None) == "signal"] or ["F.Cu", "B.Cu"]
        for nm in copper:
            layers.append({"type": "copper", "name": nm, "thickness_mm": 0.035,
                           "epsilon_r": None, "material": "copper"})
    return layers


def _laminate_height_mm(board: Board) -> float:
    setup = getattr(board, "setup", None)
    su = getattr(setup, "stackup", None) if setup else None
    if su and getattr(su, "layers", None):
        total = sum((ly.thickness or 0.0) for ly in su.layers)
        if total > 0:
            return total
    gen = getattr(board, "general", None)
    th = getattr(gen, "thickness", None) if gen else None
    return float(th) if th else 1.6


def parse_board_file(path: str) -> dict[str, Any]:
    board = Board.from_file(path)
    nets = _net_name_by_number(board)
    stackup = _stackup(board)
    height_mm = _laminate_height_mm(board)

    # per-net aggregation
    agg: dict[int, dict[str, Any]] = {}
    for item in getattr(board, "traceItems", []):
        net_no = int(getattr(item, "net", 0) or 0)
        entry = agg.setdefault(net_no, {"segments": [], "vias": 0, "via_drills": []})
        if isinstance(item, Segment):
            seg = {
                "length_m": _segment_length(item),
                "width_m": (item.width or 0.0) * 1e-3,
                "layer": item.layer,
                "x1": item.start.X, "y1": item.start.Y,
                "x2": item.end.X, "y2": item.end.Y,
            }
            entry["segments"].append(seg)
        elif isinstance(item, Via):
            entry["vias"] += 1
            if item.drill:
                entry["via_drills"].append(float(item.drill))

    nets_out = []
    for net_no, entry in sorted(agg.items()):
        name = nets.get(net_no, f"net_{net_no}")
        if not entry["segments"] and entry["vias"] == 0:
            continue
        via_drill = (sum(entry["via_drills"]) / len(entry["via_drills"])) if entry["via_drills"] else 0.3
        nets_out.append({
            "name": name,
            "number": net_no,
            "segments": entry["segments"],
            "length_mm": sum(s["length_m"] for s in entry["segments"]) * 1e3,
            "vias": entry["vias"],
            "via_drill_mm": via_drill,
            "via_span_mm": height_mm,
        })
    return {
        "nets": nets_out,
        "stackup": stackup,
        "laminate_height_mm": height_mm,
        "total_nets_in_design": len(board.nets),
        "zones": len(getattr(board, "zones", []) or []),
        "footprints": len(getattr(board, "footprints", []) or []),
    }


def stackup_for_kernel(stackup: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure the kernel sees a contiguous copper/dielectric sequence with defaults."""
    out = []
    for i, ly in enumerate(stackup):
        t = ly.get("thickness_mm")
        if t is None:
            t = 0.035 if ly["type"] == "copper" else 0.2
        d = {"type": ly["type"], "name": ly.get("name") or ("Cu" if ly["type"] == "copper" else f"diel_{i}"),
             "thickness_mm": float(t)}
        if ly["type"] != "copper":
            d["epsilon_r"] = float(ly.get("epsilon_r") or 4.3)
        out.append(d)
    return out

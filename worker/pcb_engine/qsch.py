"""QSPICE `.qsch` — byte-level reader + *additive-only* injector.

Format verified against real files (see docs/RESEARCH.md §4):
  * magic `FF D8 FF DB`
  * single-byte ASCII text lines
  * `0xAB` prefixes every record payload
  * `0xBB` terminates most record lines; a line of indent + `0xBB` alone closes a block
  * SPICE directives are `text` records whose content starts with the UTF-8 BOM
    (`EF BB BF`); multi-line bodies separated by literal `\n`
  * root element closes with a final lone `0xBB` line

Injection policy (plan T-402): we NEVER rewrite existing geometry. We append
fresh records immediately before the root's closing `0xBB`:
  1. a directive text record:  `| .include parasitics.lib`
  2. a BOM-prefixed comment text block listing extracted values + provenance
Returns brand-new bytes; originals are untouched.
"""
from __future__ import annotations

QSCH_MAGIC = b"\xff\xd8\xff\xdb"
AB = 0xAB
BB = 0xBB
BOM = b"\xef\xbb\xbf"


class QschError(Exception):
    pass


def parse(data: bytes) -> list[dict]:
    if not data.startswith(QSCH_MAGIC):
        raise QschError("not a QSPICE .qsch file (bad magic — expected FF D8 FF DB)")
    lines = data[len(QSCH_MAGIC):].split(b"\n")
    records = []
    for raw in lines:
        line = raw
        indent = len(line) - len(line.lstrip(b" "))
        body = line[indent:]
        payload = None
        if body.startswith(bytes([AB])):
            payload = body[1:]
            terminated = payload.endswith(bytes([BB]))
            if terminated:
                payload = payload[:-1]
            records.append({"indent": indent, "payload": payload,
                            "closed": terminated, "raw": raw})
        elif body == bytes([BB]):
            records.append({"indent": indent, "payload": b"", "closed": True,
                            "is_block_close": True, "raw": raw})
        else:
            records.append({"indent": indent, "payload": None, "raw": raw})
    return records


def inspect(data: bytes) -> dict:
    """Lightweight anatomy report used by the UI / pre-flight check."""
    records = parse(data)
    comps = nets = wires = junctions = directives = 0
    directive_texts: list[str] = []
    component_types: dict[str, int] = {}
    for r in records:
        p = r["payload"]
        if p is None:
            continue
        s = p.decode("latin-1")
        head = s.split(" ", 1)[0]
        if head == "component":
            comps += 1
        elif head == "symbol" and r["indent"] > 2:
            pass
        elif head == "type:":
            ctype = s.split(":", 1)[1].strip()
            component_types[ctype] = component_types.get(ctype, 0) + 1
        elif head == "net":
            nets += 1
        elif head == "wire":
            wires += 1
        elif head == "junction":
            junctions += 1
        elif head == "text" and '"' in s:
            body = s[s.find('"') + 1:s.rfind('"')]
            if body.startswith(BOM.decode("latin-1")) or s.find("\\xef\\xbb\\xbf") >= 0:
                directives += 1
                directive_texts.append(body[3:] if body.startswith("\xef\xbb\xbf") else body)
        elif head == "library":
            directives += 1
    return {"records": len(records), "components": comps, "component_types": component_types,
            "nets": nets, "wires": wires, "junctions": junctions,
            "directives": directives, "directive_texts": directive_texts,
            "magic_ok": True}


def _ascii_safe(text: str) -> str:
    """QSPICE directive payloads are latin-1-ish; keep them plain ASCII to be safe."""
    repl = {"—": "-", "–": "-", "Ω": "ohm", "µ": "u", "≥": ">=", "≤": "<=", "·": ".",
            "“": '"', "”": '"', "’": "'", "◆": "*"}
    for k, v in repl.items():
        text = text.replace(k, v)
    return text.encode("ascii", errors="replace").decode("ascii")


def _directive_text_record(x: int, y: int, text: str, size: float = 1.0, flag: int = 1) -> bytes:
    """BOM-prefixed single/multi-line directive (literal \\n separators, as QSPICE writes them)."""
    text = _ascii_safe(text)
    payload = text.replace("\\", "\\\\").replace("\n", "\\n")
    body = f'\xabtext ({x},{y}) {size:g} 7 {flag} 0x1000000 -1 -1 "{BOM.decode("latin-1")}{payload}"\xbb'
    return ("  " + body + "\n").encode("latin-1")


def inject(data: bytes, lib_filename: str, summary_lines: list[str], stamp: str) -> bytes:
    """Append the parasitics include + provenance comment block. Additive-only."""
    records = parse(data)  # validates magic
    # verification: file ends with the root-closing lone 0xBB line
    stripped = data.rstrip(b"\n")
    idx = stripped.rfind(b"\n")
    if idx < 0 or stripped[idx + 1:] != bytes([BB]):
        raise QschError("unexpected .qsch tail — refusing additive injection")
    block = b""
    block += _directive_text_record(2400, 3400, f".include {lib_filename}", 1, 1)
    block += _directive_text_record(2400, 3700, "; PCB parasitics — auto-generated " + stamp, 1, 0)
    y = 4000
    for line in summary_lines[:28]:            # keep the block compact
        block += _directive_text_record(2400, y, "; " + line, 0.8, 0)
        y += 150
    # keep a trailing newline + original root closer last
    new_data = data[:idx + 1] + block + data[idx + 1:]
    return new_data


def synth_minimal_fixture() -> bytes:
    """A tiny valid .qsch (V + R divider) built from the verified grammar — used by tests/demo."""
    out = bytearray(QSCH_MAGIC)
    out += b"\xabschematic\n"
    out += ('  \xabcomponent (2000,2000) 2 0\n'
            '    \xabsymbol R\n'
            '      \xabtype: R\xbb\n'
            '      \xabdescription: Resistor(USA Style Symbol)\xbb\n'
            '      \xabshorted pins: false\xbb\n'
            '      \xabline (0,200) (0,180) 0 0 0x1000000 -1 -1\xbb\n'
            '      \xabline (0,-180) (0,-200) 0 0 0x1000000 -1 -1\xbb\n'
            '      \xabzigzag (-80,180) (80,-180) 0 0 0 0x1000000 -1 -1\xbb\n'
            '      \xabtext (100,150) 1 7 0 0x1000000 -1 -1 "R1"\xbb\n'
            '      \xabtext (100,-150) 1 7 0 0x1000000 -1 -1 "1K"\xbb\n'
            '      \xabpin (0,200) (0,0) 1 0 0 0x0 -1 "1"\xbb\n'
            '      \xabpin (0,-200) (0,0) 1 0 0 0x0 -1 "2"\xbb\n'
            '    \xbb\n'
            '  \xbb\n').encode('latin-1')
    out += ('  \xabcomponent (2000,1000) 0 0\n'
            '    \xabsymbol C\n'
            '      \xabtype: C\xbb\n'
            '      \xabdescription: Capacitor\xbb\n'
            '      \xabshorted pins: false\xbb\n'
            '      \xabline (0,200) (0,40) 0 0 0x1000000 -1 -1\xbb\n'
            '      \xabline (0,-40) (0,-200) 0 0 0x1000000 -1 -1\xbb\n'
            '      \xabrect (-130,-40) (130,-30) 0 0 0 0x1000000 0x3000000 -1 0 -1\xbb\n'
            '      \xabrect (-130,30) (130,40) 0 0 0 0x1000000 0x3000000 -1 0 -1\xbb\n'
            '      \xabtext (130,0) 1 110 0 0x1000000 -1 -1 "C1"\xbb\n'
            '      \xabtext (-130,0) 1 109 0 0x1000000 -1 -1 "10n"\xbb\n'
            '      \xabpin (0,200) (0,0) 1 0 0 0x0 -1 "+"\xbb\n'
            '      \xabpin (0,-200) (0,0) 1 0 0 0x0 -1 "-"\xbb\n'
            '    \xbb\n'
            '  \xbb\n').encode('latin-1')
    out += ('  \xabnet (1000,1600) 1 13 0 "VIN"\xbb\n'
            '  \xabwire (1000,1600) (2000,1600) "VIN"\xbb\n'
            '  \xabwire (2000,1200) (2000,800) "SW"\xbb\n'
            '  \xabnet (2000,800) 1 14 0 "SW"\xbb\n'
            '  \xabjunction (2000,1600) 1 0\xbb\n').encode('latin-1')
    out += b'\xbb\n'
    return bytes(out)

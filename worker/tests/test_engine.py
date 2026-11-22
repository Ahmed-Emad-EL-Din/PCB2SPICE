"""Tests for the pcb parasitic engine (stdlib unittest — no pytest dependency)."""
import io
import json
import math
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pcb_engine import cir, kicad, parasitics, pipeline, qsch

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "probe_board.kicad_pcb"

SAMPLE_CIR = """* Buck converter testbench
Vin vin 0 48
R1 vin sw 0.05
L1 sw sw_int 1u
C1 sw_int 0 1n
.tran 20m
.end
"""


class ParasiticMathTests(unittest.TestCase):
    def test_skin_depth_1mhz_copper(self):
        d = parasitics.skin_depth(1e6)
        self.assertAlmostEqual(d * 1e6, 66.1, delta=1.5)  # ~66 µm @1 MHz

    def test_dc_resistance(self):
        r = parasitics.dc_resistance(1.0, 1e-3, 35e-6)
        self.assertAlmostEqual(r, 1.72e-8 / (1e-3 * 35e-6), places=10)

    def test_microstrip_reasonable(self):
        m = parasitics.microstrip(w=0.3e-3, h=0.21e-3, t=35e-6, er=4.3)
        self.assertTrue(20 < m["z0"] < 120)
        self.assertGreater(m["l_per_m"], 1e-7)

    def test_stripline_reasonable(self):
        s = parasitics.stripline(w=0.3e-3, b=0.5e-3, t=35e-6, er=4.3)
        self.assertTrue(30 < s["z0"] < 80)

    def test_via_inductance_order_of_magnitude(self):
        l = parasitics.via_inductance(1.6e-3, 0.3e-3)
        self.assertTrue(0.5e-9 < l < 2.5e-9)  # ~0.9 nH typical


class CirTransformTests(unittest.TestCase):
    PAYLOAD = {"nets": [{"name": "sw", "r_ohm": 0.02, "l_h": 5e-9, "c_f": 2e-12,
                         "f0_hz": 50e6, "method": "Tier A", "uncertainty": "±10%"}],
               "mutuals": []}

    def test_case_insensitive_node_rewrite(self):
        payload = {"nets": [{**self.PAYLOAD["nets"][0], "name": "SW"}], "mutuals": []}
        out, _, _ = cir.transform(SAMPLE_CIR, payload, "0")
        self.assertIn("R1 vin sw 0.05", out)        # boundary anchor keeps original spelling
        self.assertIn("L1 SW__PAR sw_int 1u", out)
        self.assertIn("R_PAR_SW SW SW_MIDPAR0", out)
        self.assertIn("C1 sw_int 0 1n", out)        # untouched net keeps spelling

    def test_whole_net_rewrite(self):
        # boundary rule: no independent source references 'sw' -> first referencing
        # device line (R1) anchors the original side of the ladder
        out, diff, stats = cir.transform(SAMPLE_CIR, self.PAYLOAD, "0")
        self.assertIn("R1 vin sw 0.05", out)
        self.assertIn("R_PAR_sw sw sw_MIDPAR0 0.02", out)
        self.assertIn("L_PAR_sw sw_MIDPAR0 sw__PAR 5.000000e-09", out)
        self.assertIn("C_PAR_sw sw 0 2.000000e-12", out)
        self.assertIn("L1 sw__PAR sw_int 1u", out)
        self.assertIn(".include parasitics.lib", out)
        self.assertIn(".end", out)
        self.assertNotIn("sw sw 0.05", out)             # original node gone from R1 line

    def test_idempotency_guard(self):
        out, _, _ = cir.transform(SAMPLE_CIR, self.PAYLOAD, "0")
        with self.assertRaises(ValueError):
            cir.transform(out, self.PAYLOAD, "0")

    SRC_CIR = "Vin vin 0 48\nRload vin out 1\nR1 out 0 1k\n.end\n"

    def test_independent_source_anchors_boundary(self):
        payload = {"nets": [{"name": "vin", "r_ohm": 0.05, "l_h": 10e-9, "c_f": 5e-12,
                             "f0_hz": 50e6, "method": "Tier A"}], "mutuals": []}
        out, _, _ = cir.transform(self.SRC_CIR, payload, "0")
        self.assertIn("Vin vin 0 48", out)           # source keeps original net
        self.assertIn("Rload vin__PAR out 1", out)   # consumers re-pointed
        self.assertIn("R_PAR_vin vin vin_MIDPAR0 0.05", out)

    def test_dot_commands_untouched(self):
        out, _, _ = cir.transform(SAMPLE_CIR, self.PAYLOAD, "0")
        self.assertIn(".tran 20m", out)


class QschTests(unittest.TestCase):
    def test_synth_fixture_roundtrip(self):
        data = qsch.synth_minimal_fixture()
        info = qsch.inspect(data)
        self.assertTrue(info["magic_ok"])
        self.assertGreaterEqual(info["components"], 2)
        modified = qsch.inject(data, "parasitics.lib", ["SW: R=10mΩ L=5nH C=2pF"], "2026-11-22 00:00 UTC")
        text = modified.decode("latin-1")
        self.assertIn(".include parasitics.lib", text)
        # original component records preserved byte-for-byte as prefix
        self.assertTrue(modified.startswith(data[: data.rfind(b"\n\xbb\n") + 1]))
        qsch.parse(modified)  # must not raise

    def test_bad_magic_rejected(self):
        with self.assertRaises(qsch.QschError):
            qsch.inspect(b"not a qsch")


class PipelineTests(unittest.TestCase):
    def test_analyze_fixture_board(self):
        analysis = pipeline.analyze(FIXTURE.read_bytes(), "probe_board.kicad_pcb", 50e6)
        names = [n["name"] for n in analysis["nets"]]
        self.assertIn("SW", names)
        self.assertIn("VIN", names)
        self.assertNotIn("GND", names)          # ground nets excluded from selection
        sw = next(n for n in analysis["nets"] if n["name"] == "SW")
        self.assertGreater(sw["l_h"], 0)
        self.assertGreater(sw["total_length_mm"], 20)
        self.assertTrue(sw["critical"])          # SW heuristic fires
        self.assertTrue(analysis["default_selection"])

    def test_end_to_end_zip(self):
        pcb_bytes = FIXTURE.read_bytes()
        analysis = pipeline.analyze(pcb_bytes, "probe_board.kicad_pcb", 50e6)
        selected = ["SW"]
        proj = io.BytesIO()
        with zipfile.ZipFile(proj, "w") as z:
            z.writestr("buck.cir", SAMPLE_CIR)
            z.writestr("schematic.qsch", qsch.synth_minimal_fixture())
            z.writestr("README.txt", "hello")
        result = pipeline.inject(proj.getvalue(), None, None, analysis, selected,
                                 "0", "probe_board", "probe_board.kicad_pcb")
        with zipfile.ZipFile(io.BytesIO(result["zip_bytes"])) as z:
            cir_out = z.read("buck.cir").decode()
            self.assertIn("R_PAR_SW", cir_out)
            self.assertIn(".include parasitics.lib", cir_out)
            self.assertIn("parasitics.lib", z.namelist())
            self.assertIn("PARASITICS-REPORT.html", z.namelist())
            self.assertIn("parasitics-meta.json", z.namelist())
            qsch_out = z.read("schematic.qsch").decode("latin-1")
            self.assertIn(".include parasitics.lib", qsch_out)
            self.assertEqual("hello", z.read("README.txt").decode())
        self.assertIn("SW", result["report_html"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Tier B (FastHenry2 field solver)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(ROOT))
from pcb_engine import field  # noqa: E402

_HAVE_FH = field.find_fasthenry() is not None


class TestFieldSolverInput(unittest.TestCase):
    """Input generation is testable even when the binary is absent."""

    STACKUP = [
        {"type": "copper", "name": "F.Cu", "thickness_mm": 0.035},
        {"type": "dielectric", "name": "d1", "thickness_mm": 0.2104, "epsilon_r": 4.3},
        {"type": "copper", "name": "In1.Cu", "thickness_mm": 0.035},
        {"type": "dielectric", "name": "d2", "thickness_mm": 1.065, "epsilon_r": 4.3},
        {"type": "copper", "name": "B.Cu", "thickness_mm": 0.035},
    ]

    def _seg(self, x1, y1, x2, y2, layer="F.Cu", w=0.5):
        return field.Segment3D(x1=x1, y1=y1, x2=x2, y2=y2, width_mm=w, layer=layer,
                               thickness_mm=0.035)

    def test_reference_plane_is_nearest_copper(self):
        """A trace on F.Cu must reference In1.Cu (0.21 mm), not B.Cu (1.31 mm)."""
        inp, meta = field.build_fasthenry_input(
            "SW", [self._seg(0, 0, 10, 0)], [], self.STACKUP, 1.31, 50e6)
        self.assertEqual(meta["ref_layer"], "In1.Cu")
        self.assertAlmostEqual(meta["gap_mm"], 0.2104, places=3)

    def test_sigma_uses_mm_units(self):
        """`.units mm` scales resistivity by the unit — sigma must be ~5.8e4, not 58.

        Regression: using the µm value gives 1000x too much resistance.
        """
        inp, _ = field.build_fasthenry_input(
            "SW", [self._seg(0, 0, 10, 0)], [], self.STACKUP, 1.31, 50e6)
        sigma = float(inp.split(".default sigma =")[1].split()[0])
        self.assertGreater(sigma, 1e4)
        self.assertLess(sigma, 1e5)

    def test_ipc_units_mm(self):
        inp, _ = field.build_fasthenry_input(
            "SW", [self._seg(0, 0, 10, 0)], [], self.STACKUP, 1.31, 50e6)
        self.assertIn(".units mm", inp)

    def test_plane_ref_nodes_are_continuation_lines(self):
        """npfar/npnear must be `+` continuations of the g1 block, else FastHenry
        reads them as segment definitions ('don't know what piece this is in seg')."""
        inp, _ = field.build_fasthenry_input(
            "SW", [self._seg(0, 0, 10, 0)], [], self.STACKUP, 1.31, 50e6)
        g1_idx = next(i for i, ln in enumerate(inp.splitlines()) if ln.startswith("g1 "))
        block = []
        for ln in inp.splitlines()[g1_idx + 1:]:
            if not ln.startswith("+"):
                break
            block.append(ln)
        self.assertTrue(any("npfar" in b for b in block))
        self.assertTrue(any("npnear" in b for b in block))

    def test_coincident_layers_become_one_via(self):
        """Two traces meeting at the same (x,y) on different layers → exactly one
        vertical segment (no duplicate filaments at the same center)."""
        segs = [self._seg(0, 0, 10, 0, "F.Cu"), self._seg(10, 0, 10, 10, "B.Cu")]
        inp, meta = field.build_fasthenry_input(
            "SW", segs, [], self.STACKUP, 1.31, 50e6)
        self.assertEqual(meta["n_vias_modelled"], 1)
        self.assertEqual(meta["dropped_nodes_disconnected"], 0)

    def test_no_duplicate_segments(self):
        lines = [ln for ln in field.__doc__ and [] or []]
        inp, _ = field.build_fasthenry_input(
            "SW", [self._seg(0, 0, 10, 0)], [], self.STACKUP, 1.31, 50e6)
        pairs = []
        for ln in inp.splitlines():
            if ln.startswith("e"):
                parts = ln.split()
                pairs.append(tuple(sorted((parts[1], parts[2]))))
        self.assertEqual(len(pairs), len(set(pairs)), "duplicate element definitions")


@unittest.skipUnless(_HAVE_FH, "FastHenry2 binary not installed (set FH_BIN)")
class TestFieldSolverSolve(unittest.TestCase):
    """Numerical validation — only runs when the solver is present."""

    def test_dc_resistance_matches_analytic(self):
        """10 mm x 0.3 mm x 35 µm copper, no plane: R_dc must match ρL/A."""
        inp = ("* dc check\n.units mm\n.default sigma = 58139.5\n"
               "n1 x=0 y=0 z=0\nn2 x=10 y=0 z=0\n"
               "e1 n1 n2 w=0.3 h=0.035 nhinc=1 nwinc=1\n"
               ".external n1 n2\n.freq fmin=0 fmax=0 ndec=1\n.end\n")
        res = field.run_fasthenry(inp, timeout_s=60)
        analytic = 1.72e-8 * 10e-3 / (0.3e-3 * 35e-6)
        self.assertAlmostEqual(res.r_ohm / analytic, 1.0, delta=0.02)

    def test_fixture_vin_matches_microstrip_within_10pct(self):
        """VIN is a straight trace: loop L from FastHenry must agree with the
        microstrip closed form (both include the return path)."""
        parsed = kicad.parse_board_file(str(FIXTURE))
        stackup = kicad.stackup_for_kernel(parsed["stackup"])
        vin = next(n for n in parsed["nets"] if n["name"] == "VIN")
        res, _ = field.solve_net(vin, stackup, parsed["laminate_height_mm"],
                                 50e6, seg_density=30)
        ta = parasitics.analyze_net("VIN", vin["segments"], vin["vias"],
                                    parsed["laminate_height_mm"] * 1e-3,
                                    vin["via_drill_mm"] * 1e-3, stackup, 50e6)
        self.assertAlmostEqual(res.l_h / ta.l_h, 1.0, delta=0.12)

    def test_convergence_check_reports_drift(self):
        parsed = kicad.parse_board_file(str(FIXTURE))
        stackup = kicad.stackup_for_kernel(parsed["stackup"])
        vin = next(n for n in parsed["nets"] if n["name"] == "VIN")
        conv = field.convergence_check(vin, stackup, parsed["laminate_height_mm"],
                                       50e6, densities=(20, 30))
        self.assertEqual(len(conv["points"]), 2)
        self.assertIn("l_drift", conv)
        self.assertLess(conv["l_drift"], 0.05)


class TestPipelineTiers(unittest.TestCase):
    def test_tier_a_only_never_touches_field(self):
        res = pipeline.analyze(FIXTURE.read_bytes(), "probe_board.kicad_pcb", tier="A")
        self.assertEqual(res["tier_requested"], "A")
        self.assertEqual(res["field"]["solved"], [])
        self.assertFalse(any(n.get("tier_b") for n in res["nets"]))

    def test_unknown_tier_rejected(self):
        with self.assertRaises(pipeline.PipelineError):
            pipeline.analyze(FIXTURE.read_bytes(), "probe_board.kicad_pcb", tier="Z")

    @unittest.skipUnless(_HAVE_FH, "FastHenry2 binary not installed")
    def test_tier_b_injects_field_values(self):
        """When Tier B solves, parasitics.lib must carry the FIELD R/L, not Tier A."""
        pcb = FIXTURE.read_bytes()
        analysis = pipeline.analyze(pcb, "probe_board.kicad_pcb", tier="auto")
        tb = next(n["tier_b"] for n in analysis["nets"] if n.get("tier_b"))
        payload = pipeline._net_payload(analysis, [n["name"] for n in analysis["nets"]
                                                   if n.get("tier_b")])
        for entry in payload["nets"]:
            self.assertEqual(entry["tier"], "B")
        first = payload["nets"][0]
        self.assertAlmostEqual(first["l_h"], tb["l_h"], places=12)


class PowerAndEmiAccuracyTests(unittest.TestCase):
    def test_huray_roughness_monotonic(self):
        k_low = parasitics.huray_roughness_factor(1e5)
        k_ghz = parasitics.huray_roughness_factor(1e9)
        k_10g = parasitics.huray_roughness_factor(1e10)
        self.assertGreater(k_low, 1.0)
        self.assertGreater(k_ghz, k_low)
        self.assertGreater(k_10g, k_ghz)
        self.assertLess(k_10g, 3.5)

    def test_djordjevic_sarkar_reproduces_spec_point(self):
        er_f, td_f = parasitics.djordjevic_sarkar(1e9, er_spec=4.4, tan_d_spec=0.02, f_spec=1e9)
        self.assertAlmostEqual(er_f, 4.4, places=4)
        self.assertAlmostEqual(td_f, 0.02, places=4)
        # Dispersion: er decreases slightly with frequency
        er_low, _ = parasitics.djordjevic_sarkar(1e6, er_spec=4.4, tan_d_spec=0.02, f_spec=1e9)
        er_high, _ = parasitics.djordjevic_sarkar(1e10, er_spec=4.4, tan_d_spec=0.02, f_spec=1e9)
        self.assertGreater(er_low, er_f)
        self.assertGreater(er_f, er_high)

    def test_via_capacitance_reasonable(self):
        c_via = parasitics.via_capacitance(1.6e-3, d_pad=0.6e-3, d_antipad=1.1e-3, er=4.4)
        self.assertTrue(0.2e-12 < c_via < 1.0e-12, c_via)

    def test_copper_resistivity_temp_derating(self):
        r20 = parasitics.copper_resistivity(20.0)
        r70 = parasitics.copper_resistivity(70.0)
        self.assertAlmostEqual(r20, parasitics.RHO_CU, places=14)
        self.assertAlmostEqual(r70 / r20, 1.0 + 0.00393 * 50.0, places=6)

    def test_ipc2152_ampacity(self):
        i_ext = parasitics.ipc2152_ampacity(2.0e-3, 35e-6, delta_t_c=20.0, external=True)
        i_int = parasitics.ipc2152_ampacity(2.0e-3, 35e-6, delta_t_c=20.0, external=False)
        self.assertAlmostEqual(i_ext / i_int, 2.0, places=6)
        self.assertTrue(2.0 < i_ext < 10.0, i_ext)

    def test_emi_metrics_physics(self):
        m = parasitics.emi_metrics(
            l_loop_h=10e-9,
            c_sw_f=100e-12,
            f_hz=1e6,
            i_sw_a=10.0,
            dv_dt_v_ns=20.0,
            loop_area_m2=1e-4,
            dist_m=3.0,
        )
        # I_CM = 100 pF * 20 V/ns = 2.0 A
        self.assertAlmostEqual(m["i_cm_a"], 2.0, places=6)
        # f_ring = 1 / (2*pi*sqrt(10 nH * 100 pF)) = 159.155 MHz
        self.assertAlmostEqual(m["f_ring_hz"] / 1e6, 159.1549, places=2)
        # Z_ring = sqrt(10 nH / 100 pF) = 10 Ohm
        self.assertAlmostEqual(m["z_ring_ohm"], 10.0, places=6)
        self.assertGreater(m["e_dm_dbuv_m"], 0.0)

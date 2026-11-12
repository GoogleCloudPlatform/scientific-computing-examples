#!/usr/bin/env python3
"""Unit tests for science_skills_bridge.py."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from science_skills_bridge import (
    analyze_afdb_for_md,
    convert_chembl_to_htvs,
    enrich_docking_hits,
    generate_variant_analysis_plan,
    normalize_concentration_to_nm,
)


class TestScienceSkillsBridgeStandalone(unittest.TestCase):
    def test_normalize_concentration_to_nm(self):
        self.assertAlmostEqual(normalize_concentration_to_nm(2.5, "uM"), 2500.0)
        self.assertAlmostEqual(normalize_concentration_to_nm(10, "nM"), 10.0)
        self.assertAlmostEqual(normalize_concentration_to_nm(100, "pM"), 0.1)
        self.assertAlmostEqual(normalize_concentration_to_nm(0.5, "ug/mL", mw=500.0), 1000.0)
        self.assertIsNone(normalize_concentration_to_nm(0.5, "ug/mL"))
        self.assertIsNone(normalize_concentration_to_nm(-1, "nM"))

    def test_afdb_gatekeeper_disorder_and_pae_detection(self):
        # High disorder N/C tails + single-residue terminal spike + internal disordered linker
        plddts = [95.0] + [30.0] * 34 + [92.0] * 60 + [35.0] * 25 + [90.0] * 40 + [35.0] * 35
        # 2D PAE matrix (195x195) with two independent rigid blocks and high inter-domain PAE (22.0 A)
        n = len(plddts)
        pae_matrix = [
            [3.0 if (i < 100 and j < 100) or (i >= 100 and j >= 100) else 22.0 for j in range(n)]
            for i in range(n)
        ]
        res = analyze_afdb_for_md(
            uniprot_id="P12345",
            residue_plddts=plddts,
            pae_data=pae_matrix,
            gpus=8,
            gpu_type="H100",
            cpu_cores=88,
            nodes=1,
        )
        self.assertTrue(res["needs_domain_cropping"])
        self.assertIsNotNone(res["disorder_gatekeeper_warning"])
        # Single-residue spike at residue 1 should be ignored; core starts at 36
        self.assertEqual(res["recommended_core_domain"]["start_residue"], 36)
        self.assertGreaterEqual(len(res["internal_disordered_linkers"]), 1)
        self.assertGreater(res["pae_metrics"]["inter_domain_pae"], 15.0)
        self.assertGreaterEqual(len(res["pae_rigid_domains"]), 2)
        self.assertLess(
            res["estimated_solvated_atoms"]["cropped_core"],
            res["estimated_solvated_atoms"]["full_length"],
        )
        # Verify upstream science-skills CLI invocations
        self.assertIn("fetch_structure.py P12345 --output-dir", res["science_skills_commands"]["fetch_afdb"])
        self.assertIn("AF-P12345-F1-metadata.json", res["science_skills_commands"]["analyze_plddt"])
        self.assertIn("uniprot_tools.py get P12345", res["science_skills_commands"]["uniprot_active_sites"])

    def test_chembl_htvs_conversion_and_enrichment(self):
        records = [
            {
                "molecule_chembl_id": "CHEMBL203_A",
                "canonical_smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1",
                "pref_name": "ANALOG_A",
                "standard_value": "0.05",
                "standard_units": "uM",
                "max_phase": 3,
                "num_ro5_violations": 0,
            },
            {
                "molecule_chembl_id": "CHEMBL_PCT_INHIB",
                "canonical_smiles": "CC1=CC=CC=C1",
                "standard_value": "85.0",
                "standard_units": "%",
            },
            {
                "molecule_chembl_id": "CHEMBL_UG_ML_WITH_MW",
                "canonical_smiles": "CCC1=CC=CC=C1",
                "standard_value": "0.1",
                "standard_units": "ug/mL",
                "full_mwt": "500.0",  # 200 nM <= 500 nM
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            smi_out = os.path.join(tmpdir, "out.smi")
            conv = convert_chembl_to_htvs(records, output_smi_path=smi_out, max_activity_nm=500.0)
            self.assertEqual(conv["accepted_molecules"], 2)
            self.assertEqual(conv["skipped_breakdown"]["non_molar_units"], 1)
            self.assertTrue(os.path.isfile(smi_out))

            enriched = enrich_docking_hits(
                docking_hits=[{"molecule": "CHEMBL203_A", "affinity_kcal_mol": -9.6}],
                chembl_metadata=records,
            )
            self.assertEqual(enriched[0]["pref_name"], "ANALOG_A")
            self.assertAlmostEqual(enriched[0]["experimental_activity_nm"], 50.0)

    def test_variant_plan(self):
        plan = generate_variant_analysis_plan(["chr7:140753336:A>T"])
        self.assertEqual(plan["total_variants"], 1)
        self.assertIn("ALPHAGENOME_API_KEY", plan["required_env"])
        wf = plan["variant_workflows"][0]
        self.assertIn('alphagenome_atlas_avi.py query "chr7:140753336:A>T"', wf["alphagenome_avi_triage"])
        self.assertIn("--chrom chr7 --pos 140753336 --ref A --alt T", wf["alphagenome_effect_prediction"])
        self.assertIn('get_variant_frequency.py --variant_id "7-140753336-A-T"', wf["gnomad_frequency"])


if __name__ == "__main__":
    unittest.main()


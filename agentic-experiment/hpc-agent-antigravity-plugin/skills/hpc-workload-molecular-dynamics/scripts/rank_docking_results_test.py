import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rank_docking_results import parse_vina_logs

class TestRankDockingResults(unittest.TestCase):
    def test_single_and_multi_molecule_batch_extraction(self):
        log_single = """
AutoDock Vina v1.2.5
Reading input ... done.
Performing docking ...
mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1         -8.5      0.000      0.000
   2         -8.1      1.234      2.345
"""
        log_multi = """
AutoDock Vina v1.2.5
Ligand: CID_1001
mode |   affinity | dist from best mode
-----+------------+----------+----------
   1         -9.7      0.000      0.000
   2         -9.2      1.100      2.100

Ligand: CID_1002
mode |   affinity | dist from best mode
-----+------------+----------+----------
   1         -7.2      0.000      0.000

Ligand: CID_1003
mode |   affinity | dist from best mode
-----+------------+----------+----------
   1        -11.4      0.000      0.000
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "mol_single.log"), "w") as f:
                f.write(log_single)
            with open(os.path.join(tmpdir, "batch_docking.log"), "w") as f:
                f.write(log_multi)

            csv_out = os.path.join(tmpdir, "leads.csv")
            hits = parse_vina_logs(tmpdir, top_n=10, output_csv=csv_out)

            self.assertEqual(len(hits), 4)
            # Verify ranked in ascending order (best binding affinity lowest kcal/mol)
            self.assertEqual(hits[0]["molecule"], "CID_1003")
            self.assertAlmostEqual(hits[0]["affinity_kcal_mol"], -11.4)

            self.assertEqual(hits[1]["molecule"], "CID_1001")
            self.assertAlmostEqual(hits[1]["affinity_kcal_mol"], -9.7)

            self.assertEqual(hits[2]["molecule"], "mol_single")
            self.assertAlmostEqual(hits[2]["affinity_kcal_mol"], -8.5)

            self.assertEqual(hits[3]["molecule"], "CID_1002")
            self.assertAlmostEqual(hits[3]["affinity_kcal_mol"], -7.2)

            self.assertTrue(os.path.exists(csv_out))

if __name__ == "__main__":
    unittest.main()

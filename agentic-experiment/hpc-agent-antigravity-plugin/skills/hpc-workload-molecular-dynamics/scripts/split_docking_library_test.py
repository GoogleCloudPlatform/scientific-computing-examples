import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split_docking_library import detect_format, split_library

class TestSplitDockingLibrary(unittest.TestCase):
    def test_format_detection(self):
        self.assertEqual(detect_format("library.sdf"), "sdf")
        self.assertEqual(detect_format("compounds.pdbqt"), "pdbqt")
        self.assertEqual(detect_format("ligands.smi"), "smi")
        self.assertEqual(detect_format("database.csv"), "csv")

    def test_split_sdf(self):
        sdf_content = """Mol1
  -OEChem-08282601012D

  1  0  0     0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
Mol2
  -OEChem-08282601012D

  1  0  0     0  0  0  0  0  0  0999 V2000
    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
Mol3
  -OEChem-08282601012D

  1  0  0     0  0  0  0  0  0  0999 V2000
    2.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
M  END
$$$$
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "input.sdf")
            with open(input_file, "w") as f:
                f.write(sdf_content)
                
            chunks = split_library(input_file, chunk_size=2, output_dir=os.path.join(tmpdir, "chunks"), file_format="sdf")
            self.assertEqual(len(chunks), 2)
            self.assertTrue(os.path.exists(chunks[0]))
            self.assertTrue(os.path.exists(chunks[1]))

    def test_split_pdbqt(self):
        pdbqt_content = """MODEL 1
REMARK Ligand 1
ATOM      1  C   UNL     1       0.000   0.000   0.000  0.00  0.00     +0.000 C
ENDMDL
MODEL 2
REMARK Ligand 2
ATOM      1  C   UNL     2       1.000   0.000   0.000  0.00  0.00     +0.000 C
ENDMDL
MODEL 3
REMARK Ligand 3
ATOM      1  C   UNL     3       2.000   0.000   0.000  0.00  0.00     +0.000 C
ENDMDL
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "input.pdbqt")
            with open(input_file, "w") as f:
                f.write(pdbqt_content)
                
            chunks = split_library(input_file, chunk_size=2, output_dir=os.path.join(tmpdir, "chunks"), file_format="pdbqt")
            self.assertEqual(len(chunks), 2)

    def test_split_csv_header_preservation(self):
        csv_content = """smiles,id,activity
CCO,mol_1,1.2
CCN,mol_2,3.4
CCC,mol_3,5.6
CCF,mol_4,7.8
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "input.csv")
            with open(input_file, "w") as f:
                f.write(csv_content)
                
            chunks = split_library(input_file, chunk_size=2, output_dir=os.path.join(tmpdir, "chunks"), file_format="csv")
            self.assertEqual(len(chunks), 2)
            with open(chunks[0]) as f:
                lines = f.readlines()
                self.assertTrue(lines[0].startswith("smiles,id"))
                self.assertEqual(len(lines), 3) # header + 2 records
            with open(chunks[1]) as f:
                lines = f.readlines()
                self.assertTrue(lines[0].startswith("smiles,id"))

if __name__ == "__main__":
    unittest.main()

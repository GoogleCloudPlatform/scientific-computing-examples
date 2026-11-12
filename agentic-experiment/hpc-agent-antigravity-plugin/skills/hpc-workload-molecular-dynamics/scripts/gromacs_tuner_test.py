import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gromacs_tuner import tune_gromacs

class TestGromacsTuner(unittest.TestCase):
    def test_b200_tuning(self):
        res = tune_gromacs(atoms=300000, gpus=8, gpu_type="B200", cpu_cores=192, nodes=1)
        self.assertEqual(res["mpi_ranks"], 8)
        self.assertEqual(res["threads_per_rank"], 24)
        self.assertEqual(res["offload_mode"], "FULL_GPU_RESIDENT")
        self.assertIn("-nb gpu -pme gpu -bonded gpu -update gpu", res["offload_flags"])
        self.assertIn("-ntmpi 8", res["command"])
        self.assertIn("-ntomp 24", res["command"])

    def test_h100_tuning_hybrid(self):
        res = tune_gromacs(atoms=800000, gpus=8, gpu_type="H100", cpu_cores=88, nodes=1)
        self.assertEqual(res["mpi_ranks"], 8)
        self.assertEqual(res["threads_per_rank"], 11)
        self.assertEqual(res["offload_mode"], "HYBRID_GPU")
        self.assertIn("-nb gpu -pme gpu -bonded gpu", res["offload_flags"])
        self.assertNotIn("-update gpu", res["offload_flags"])

    def test_multinode_pme_rank_recommendation(self):
        res = tune_gromacs(atoms=2000000, gpus=8, gpu_type="H100", cpu_cores=88, nodes=4)
        self.assertEqual(res["mpi_ranks"], 32)
        self.assertEqual(res["nodes"], 4)
        self.assertGreater(res["pme_ranks"], 0)
        self.assertEqual(res["pme_ranks"], 8)  # 32 // 4 = 8 PME ranks
        self.assertIn("-npme 8", res["command"])
        self.assertIn("mpirun -np 32 gmx_mpi mdrun", res["command"])

    def test_cpu_tuning(self):
        res = tune_gromacs(atoms=50000, gpus=0, gpu_type="None", cpu_cores=192, nodes=1)
        self.assertEqual(res["mpi_ranks"], 96)
        self.assertEqual(res["threads_per_rank"], 2)
        self.assertEqual(res["offload_mode"], "CPU_ONLY")
        self.assertIn("-ntmpi 96", res["command"])
        self.assertIn("-ntomp 2", res["command"])

if __name__ == "__main__":
    unittest.main()

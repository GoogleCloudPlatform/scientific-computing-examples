import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decompose_helper import factorize_3d

class TestDecomposeHelper(unittest.TestCase):
    def test_factorize_3d_h3(self):
        nx, ny, nz = factorize_3d(88)
        self.assertEqual(nx * ny * nz, 88)

    def test_factorize_3d_c4_192(self):
        nx, ny, nz = factorize_3d(192)
        self.assertEqual(nx * ny * nz, 192)

    def test_factorize_3d_c4d_384(self):
        nx, ny, nz = factorize_3d(384)
        self.assertEqual(nx * ny * nz, 384)

    def test_factorize_3d_prime(self):
        nx, ny, nz = factorize_3d(97)
        self.assertEqual(nx * ny * nz, 97)

    def test_factorize_3d_multinode_h3(self):
        nx, ny, nz = factorize_3d(176)
        self.assertEqual(nx * ny * nz, 176)

if __name__ == "__main__":
    unittest.main()

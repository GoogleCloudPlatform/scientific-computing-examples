import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from residual_parser import parse_fluent_log, parse_openfoam_log

class TestResidualParser(unittest.TestCase):
    def test_openfoam_scientific_notation_and_eof_flush(self):
        log_content = """
Time = 1.000000e-03

Solving for Ux, Initial residual = 0.5, Final residual = 1.234e-05, No Iterations 1
Solving for Uy, Initial residual = 0.5, Final residual = 2.345e-05, No Iterations 1
Solving for p_rgh, Initial residual = 0.8, Final residual = 3.456e-05, No Iterations 2
Solving for nuTilda, Initial residual = 0.1, Final residual = 4.567e-06, No Iterations 1
Solving for h, Initial residual = 0.2, Final residual = 5.678e-05, No Iterations 1
Solving for gammaInt, Initial residual = 0.3, Final residual = 6.789e-05, No Iterations 1
Solving for ReThetat, Initial residual = 0.4, Final residual = 7.890e-05, No Iterations 1
Solving for pcorr, Initial residual = 0.5, Final residual = 8.901e-05, No Iterations 1

Time = 2.000000e-03

Solving for Ux, Initial residual = 0.01, Final residual = 1.0e-06, No Iterations 1
Solving for T, Initial residual = 0.02, Final residual = 2.0e-06, No Iterations 1
Solving for e, Initial residual = 0.03, Final residual = 3.0e-06, No Iterations 1
"""
        with tempfile.NamedTemporaryFile("w+", delete=True) as tmp:
            tmp.write(log_content)
            tmp.flush()
            history = parse_openfoam_log(tmp.name)

        self.assertEqual(len(history), 2)
        # Check first timestep
        self.assertEqual(history[0]["time"], "1.000000e-03")
        self.assertAlmostEqual(history[0]["residuals"]["p_rgh"], 3.456e-05)
        self.assertAlmostEqual(history[0]["residuals"]["nuTilda"], 4.567e-06)
        self.assertAlmostEqual(history[0]["residuals"]["h"], 5.678e-05)
        self.assertAlmostEqual(history[0]["residuals"]["gammaInt"], 6.789e-05)
        self.assertAlmostEqual(history[0]["residuals"]["ReThetat"], 7.890e-05)
        self.assertAlmostEqual(history[0]["residuals"]["pcorr"], 8.901e-05)

        # Check second timestep (flushed at EOF)
        self.assertEqual(history[1]["time"], "2.000000e-03")
        self.assertAlmostEqual(history[1]["residuals"]["Ux"], 1.0e-06)
        self.assertAlmostEqual(history[1]["residuals"]["T"], 2.0e-06)
        self.assertAlmostEqual(history[1]["residuals"]["e"], 3.0e-06)

    def test_fluent_parser(self):
        fluent_log = """
  iter  continuity  x-velocity  y-velocity  z-velocity  k  epsilon     time/iter
     1  1.0000e+00  1.0000e+00  1.0000e+00  1.0000e+00  1.0000e+00  1.0000e+00  0:00:00   20
     2  5.2345e-02  4.1234e-02  3.9876e-02  3.1234e-02  2.5678e-02  2.1234e-02  0:00:01   19
     3  8.4521e-05  7.1234e-05  6.9876e-05  5.1234e-05  4.5678e-05  3.1234e-05  0:00:02   18
!       solution is converged
"""
        with tempfile.NamedTemporaryFile("w+", delete=True) as tmp:
            tmp.write(fluent_log)
            tmp.flush()
            history = parse_fluent_log(tmp.name)

        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1]["time"], "3")
        self.assertAlmostEqual(history[-1]["residuals"]["continuity"], 8.4521e-05)
        self.assertAlmostEqual(history[-1]["residuals"]["x-velocity"], 7.1234e-05)
        self.assertAlmostEqual(history[-1]["residuals"]["k"], 4.5678e-05)
        self.assertAlmostEqual(history[-1]["residuals"]["epsilon"], 3.1234e-05)

if __name__ == "__main__":
    unittest.main()

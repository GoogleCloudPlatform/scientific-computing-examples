from PhysicsInformed import PhysicsInformedBarModel
import numpy as np
import torch
import unittest
import utilities
import torch


class TestPhysicsInformed(unittest.TestCase):
    def setUp(self):
        self.E = lambda x: 2.
        self.A = lambda x: x + 1.
        self.L = 3.
        self.uB = [[0, 0, 0], [1, 1, -1]]
        self.dist_Load = lambda x: x
        self.testModel = PhysicsInformedBarModel(self.E,
                                                                 self.A,
                                                                 self.L,
                                                                 self.uB,
                                                                 dist_load=self.dist_Load)

    def testGenerateGrid1D(self):
        x = torch.tensor([[0.0000],
                          [0.333333333],
                          [0.666666667],
                          [1.000000000],
                          [1.333333333],
                          [1.666666667],
                          [2.000000000],
                          [2.333333333],
                          [2.666666667],
                          [3.000000000]], )
        np.testing.assert_almost_equal(x.tolist(),
                                       utilities.generateGrid1d(self.L, samples=10).detach().tolist(),
                                       decimal=4)

    def testCostFunction(self):
        x = utilities.generateGrid1d(self.L)
        u = x ** 3 - x ** 2 + 2
        costTest = self.testModel.costFunction(x, u)
        self.assertAlmostEqual(
            costTest[0].detach().numpy()[0],
            130680.52,
            places=2)
        self.assertAlmostEqual(
            costTest[1].detach().numpy()[0],
            404.0,
            places=2)

    def testTrain(self):
        self.testModel.model[0].weight.data = torch.zeros(40, 1)
        self.testModel.model[2].weight.data = torch.ones(1, 40)
        self.testModel.model[0].bias.data = torch.ones(40) * 3
        self.testModel.model[2].bias.data = torch.ones(1) * 5

        self.testModel.train(2000, optimizer='Adam', lr=1e-3)

        x = utilities.generateGrid1d(self.L, 30, 0)
        u = self.testModel.getDisplacements(x)
        costTest = self.testModel.costFunction(x, u)

        self.assertAlmostEqual(
            costTest[0].detach().numpy()[0],
            2.0974,
            places=3)
        self.assertAlmostEqual(
            costTest[1].detach().numpy()[0],
            24.8166,
            places=3)


unittest.main()  # Run the unittest. 
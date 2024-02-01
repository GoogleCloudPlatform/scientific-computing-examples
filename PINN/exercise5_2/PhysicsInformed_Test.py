from PhysicsInformed import InversePhysicsInformedBarModel
import numpy as np
import torch
import unittest
import utilities
import torch


class TestPhysicsInformed(unittest.TestCase):
    def setUp(self):
        self.L = 2.
        self.x = utilities.generateGrid1d(self.L, 30)
        self.u = torch.sin(self.x)
        self.dist_Load = lambda x: x
        self.testModel = InversePhysicsInformedBarModel(self.L,
                                                        self.dist_Load)

    def testPredict(self):
        self.testModel.model[0].weight.data = torch.ones(20, 2) * 2
        self.testModel.model[2].weight.data = torch.ones(1, 20) * 0.2
        self.testModel.model[0].bias.data = torch.ones(20) * 3
        self.testModel.model[2].bias.data = torch.ones(1) * 5

        x = torch.tensor([[8.9802],
                          [8.9886],
                          [8.9934],
                          [8.9962],
                          [8.9978],
                          [8.9987],
                          [8.9992],
                          [8.9996],
                          [8.9997],
                          [8.9998],
                          [8.9999],
                          [8.9999],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000],
                          [9.0000]], )
        np.testing.assert_almost_equal(x.tolist(),
                                       self.testModel.predict(self.x, self.u).detach().tolist(),
                                       decimal=4)

    def testCostFunction(self):
        EA = torch.ones(30, 1) * 25
        costTest = self.testModel.costFunction(self.x, self.u, EA).detach().numpy()[0]
        self.assertAlmostEqual(
            costTest,
            9765.3418,
            places=4)

    def testTrain(self):
        self.testModel.model[0].weight.data = torch.ones(20, 2) * 22
        self.testModel.model[2].weight.data = torch.ones(1, 20) * (-2)
        self.testModel.model[0].bias.data = torch.ones(20) * 0.1
        self.testModel.model[2].bias.data = torch.ones(1) * 2

        self.testModel.train(self.x, self.u, 1000, optimizer='Adam', lr=1e-2)
        EA = torch.ones(30, 1)
        costTest = self.testModel.costFunction(self.x, self.u, EA).detach().numpy()[0]

        self.assertAlmostEqual(
            costTest,
            6.0165005,
            places=4)


unittest.main()  # Run the unittest. 
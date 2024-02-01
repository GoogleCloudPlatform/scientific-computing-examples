from PhysicsInformed import PhysicsInformedBarModel
import utilities
import numpy as np
import torch

# Analytial solution
u_analytic = lambda x: (1. - np.cos(3. * np.pi * x))

# Problem data
E = lambda x: 1. 
A = lambda x: x ** 2 + 1.
L = 3. / 2.
uB = [[0, 0, 0], [0, 1, 0]]
distLoad = lambda x: -6 * x * np.pi * torch.sin(3 * np.pi * x) - 9 * (x ** 2 + 1) * np.pi ** 2 * torch.cos(
    3 * np.pi * x)

# Generate model
pinnModel = PhysicsInformedBarModel(E, A, L, uB, dist_load=distLoad)

# Train model
#pinnModel.train(epochs=6000, optimizer='Adam', lr=5e-3)

pinnModel.train(epochs=600, optimizer='LBFGS', lr=1e-2)

# Test data
samples = 100
x_test = utilities.generateGrid1d(L, samples)
u_test = pinnModel.getDisplacements(x_test)

# Plot displacements
utilities.plotDisplacementsBar(x_test, u_test, u_analytic)

# Plot training history
pinnModel.plotTrainingHistory()


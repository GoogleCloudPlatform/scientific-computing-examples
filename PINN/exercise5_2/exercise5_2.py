from PhysicsInformed import InversePhysicsInformedBarModel
import utilities
import torch
import math
import matplotlib.pyplot as plt
import numpy as np

# Analytic solution
EA_analytic = lambda x: np.sqrt(2*math.sin(1)*x-2*np.sin(x)+1)

# Problem data
L = 1
x = utilities.generateGrid1d(L, 20)
u_analytic = lambda x: 1-torch.sqrt(2*math.sin(1)*x-2*torch.sin(x)+1)
u = u_analytic(x)
distLoad = lambda x: torch.sin(x)

# Generate model
pinnModel = InversePhysicsInformedBarModel(L, distLoad)

# Train model
#pinnModel.train(x, u, epochs=10000, optimizer='Adam', lr=1e-2)
pinnModel.train(x, u, epochs=500, optimizer='LBFGS', lr=5e-2)

# Test model
samples = 100
x_test = utilities.generateGrid1d(L, samples)
u_test = u_analytic(x_test)
EA_test = pinnModel.predict(x_test,u_test)

# Plot stiffness
utilities.plotStiffnessBar(x_test, EA_test, EA_analytic)

# Plot training history
pinnModel.plotTrainingHistory()

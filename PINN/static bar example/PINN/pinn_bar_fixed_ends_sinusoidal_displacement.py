from physicsinformed import PhysicsInformedBarModel
import utilities
import numpy as np
import torch
import matplotlib.pyplot as plt

# Analytic solution
u_analytic = lambda x: np.sin(2 * np.pi * x / L)

# Problem data
E = lambda x: 1
A = lambda x: 1
L = 1
u0 = [0,0]  # Dirichlet boundary conditions for both edges
distLoad = lambda x: 4 * np.pi**2 * E(x) * A(x) / L**2 * torch.sin(2 * np.pi * x / L)

# Generate model
pinnModel = PhysicsInformedBarModel(E, A, L, u0, dist_load=distLoad)

# Train model
epochs = 10000
learningRate = 1e-3
weightDecay = 0.1
bcWeight=10
#pinnModel.train(epochs, lr=learningRate)

pinnModel.train(50, optimizer='LBFGS', lr=1e-1)

# Test data
samples = 100
x_test = utilities.generate_grid_1d(L, samples)
u_test = pinnModel.get_displacements(x_test)

# Plot displacements
utilities.plot_displacements_bar(x_test, u_test, u_analytic)

filename = "displacements_bar_pinn"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")

# Plot training history
pinnModel.plot_training_history()

filename = "training_history_bar_pinn"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")




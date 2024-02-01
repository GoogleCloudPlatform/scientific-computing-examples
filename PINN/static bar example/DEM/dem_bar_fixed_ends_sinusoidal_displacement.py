import utilities
from deepenergy import DeepEnergyBarModel
import numpy as np
import torch
import matplotlib.pyplot as plt

# Manufactured solution
u_analytic = lambda x: np.sin(2 * np.pi * x / L)
e_analytic = lambda x: 2 * np.pi / L * torch.cos(2 * np.pi * x / L)

# Problem data
E = lambda x: 1
A = lambda x: 1
L = 1
dirichlet_bc = 'fixed_both'
dist_load = lambda x: 4 * np.pi**2 * E(x) * A(x) / L**2 * torch.sin(2 * np.pi * x / L)

# Generate model
dem_model = DeepEnergyBarModel(E, A, L, dirichlet_bc, dist_load=dist_load)

# Train model
#epochs = 25000
epochs = 7000
learning_rate = 5e-3
weight_decay = 0

#dem_model.train(epochs, optimizer='Adam', lr=learning_rate)

#dem_model.train(20, optimizer='LBFGS', lr=1e-1)
dem_model.train(50, optimizer='LBFGS', lr=1e-1)

# Test model
samples = 100
x_test = utilities.generate_grid_1d(L, samples)
u_test = dem_model.get_displacements(x_test)

# Plot displacements
utilities.plot_displacements_bar(x_test, u_test, u_analytic)

filename = "displacements_bar_dem_overfit"
#filename = "displacements_bar_dem"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")

# Plot training history
dem_model.plot_training_history()

filename = "training_history_bar_dem_overfit"
#filename = "training_history_bar_dem"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")









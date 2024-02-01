import utilities
from physicsinformed import InversePhysicsInformedBarModel
import torch
import math
import matplotlib.pyplot as plt

# Problem data
L = 1
x = utilities.generate_grid_1d(L, 20)
u_analytic = lambda x: torch.sin(2*math.pi*x)
u = u_analytic(x)

#distLoad = lambda x: ((x+1)*4*math.pi**2*torch.sin(2*math.pi*x)-2*math.pi*torch.cos(2*math.pi*x))
distLoad = lambda x: -2*(3*x**2 - 2*x)*math.pi*torch.cos(2*math.pi*x) + 4*(x**3 - x**2 + 1)*math.pi**2*torch.sin(2*math.pi*x)
u0 = [[0,0],[0,-1]]

#EA_analytic = lambda x: x+1
EA_analytic = lambda x: x**3 - x**2 + 1

# Generate model
pinnModel = InversePhysicsInformedBarModel(x, u, L, distLoad)

# Train model
epochs = 5000
learningRate = 8e-3
weightDecay = 0.1
#pinnModel.train(epochs, lr=learningRate)

pinnModel.train(50, optimizer='LBFGS', lr=1e-1)

# Test model
samples = 100
x_test = utilities.generate_grid_1d(L, samples)
u_test = u_analytic(x_test)
EA_test = pinnModel.predict(x_test,u_test)

# Plot stiffness
utilities.plot_stiffness_bar(x_test, EA_test, EA_analytic)

filename = "stiffness_bar_pinninv"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")

# Plot training history
pinnModel.plot_training_history()


filename = "training_history_bar_pinninv"
plt.savefig(filename + ".eps")
plt.savefig(filename + ".png")







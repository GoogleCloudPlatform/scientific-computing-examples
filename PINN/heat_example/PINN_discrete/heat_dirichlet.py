import time
import torch
import numpy as np
import scipy.io
from physicsinformed import PhysicsInformedDiscrete
from scipy.interpolate import griddata
import utilities

# Select gpu if available
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
dtype = torch.float

# Set seed for the Random Number Generator (RNG)
torch.manual_seed(0)
np.random.seed(0)

q = 50
layers = [1, 20, 20, 20, q+1]
lb = np.array([0])
ub = np.array([1.0])

N = 200
epochs_Adam = 10000
epochs_LBFGS = 100

data = scipy.io.loadmat('data/heat1Dnorm.mat')

t = data['ts'].flatten()[:, None]  # T x 1
x = data['xs'].flatten()[:, None]  # N x 1
Exact = np.real(data['usol']).T  # T x N

idx_t0 = 20
idx_t1 = 120
t0 = torch.tensor(t[idx_t0], dtype=dtype, requires_grad=False, device=device)
dt = torch.tensor(t[idx_t1] - t[idx_t0], dtype=dtype, requires_grad=False, device=device)

# Initial data
idx_x = np.random.choice(Exact.shape[1], N, replace=False)
x0 = torch.tensor(x[idx_x, :], dtype=dtype, requires_grad=True, device=device)
u0 = torch.tensor(Exact[idx_t0:idx_t0 + 1, idx_x].T, dtype=dtype, requires_grad=False, device=device)
print(x0.size())

### TRAINING ###
# Initialize PINN model
PINNModel = PhysicsInformedDiscrete(layers, x0, u0, t0, dt, q)

# Train the model
start_time = time.time()
PINNModel.train(epochs_Adam, optimizer='Adam', lr=0.001)
PINNModel.train(epochs_LBFGS, optimizer='L-BFGS')
elapsed = time.time() - start_time
print('Training time: %.4f' % (elapsed))

# Test data
x_star = torch.tensor(x, dtype=dtype, requires_grad=False, device=device)

U1_pred = PINNModel.U1_nn(x_star).detach().cpu().numpy()

error = np.linalg.norm(U1_pred[:, -1] - Exact[idx_t1, :], 2) / np.linalg.norm(Exact[idx_t1, :], 2)
print('Error: %e' % (error))

# Plot training history and predicitons
PINNModel.plot_training_history()

x0 = x0.detach().cpu().numpy()
u0 = u0.detach().cpu().numpy()
x_star = x_star.detach().cpu().numpy()

utilities.plot_results(t, x, x0, u0, x_star, U1_pred, Exact, lb, ub, idx_t0, idx_t1)

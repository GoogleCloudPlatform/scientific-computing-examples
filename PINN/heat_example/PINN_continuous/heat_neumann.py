import time
import torch
import numpy as np
import scipy.io
from pyDOE import lhs
from physicsinformed import PhysicsInformedContinuous
from scipy.interpolate import griddata
import utilities

# Select gpu if available
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
dtype = torch.float

# Set seed for the Random Number Generator (RNG)
torch.manual_seed(0)
np.random.seed(0)

# Define no. of training points
N0 = 100
N_b = 50
N_f = 20000

# Define feed-forward network architecture
layers = [2, 20, 20, 20, 1]

# Define no. of epochs for each optimizer
epochs_Adam = 4000
epochs_LBFGS = 1000

### PRE-PROCESSING ###
# Loading benchmark data
data = scipy.io.loadmat('data/heat1Dscript.mat')
t = data['ts'].flatten()[:, None]
x = data['xs'].flatten()[:, None]
u_sol = data['usol'].T
flux_sol = data['fluxsol'].T

X, T = np.meshgrid(x, t)

# Transform grid into vectors that can be processed by the neural net
X_star = np.hstack((X.flatten()[:, None], T.flatten()[:, None]))
u_star = u_sol.flatten()[:, None]
flux_star = flux_sol.flatten()[:, None]

# Domain bounds
lb = X_star.min(0)
ub = X_star.max(0)

# Select random data points for the initial condition
idx_x = np.random.choice(x.shape[0], N0, replace=False)
x0 = x[idx_x, :]
u0 = torch.tensor(u_sol.T[idx_x, 0:1], dtype=dtype, device=device)

# Select random data points for the boundary condition
idx_t = np.random.choice(t.shape[0], N_b, replace=False)
tb = t[idx_t, :]

# Create collocation points with latin hypercube sampling
X_f = lb + (ub - lb) * lhs(2, N_f)

X0 = np.concatenate((x0, 0 * x0), 1) # (x0, 0)
X_lb = np.concatenate((0 * tb + lb[0], tb), 1) # (lb[0], tb)
X_ub = np.concatenate((0 * tb + ub[0], tb), 1) # (ub[0], tb)

### TRAINING ###
# Create torch.tensors of training data
x0 = torch.tensor(X0[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t0 = torch.tensor(X0[:, 1:2], dtype=dtype, requires_grad=True, device=device)

x_lb = torch.tensor(X_lb[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t_lb = torch.tensor(X_lb[:, 1:2], dtype=dtype, requires_grad=True, device=device)

x_ub = torch.tensor(X_ub[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t_ub = torch.tensor(X_ub[:, 1:2], dtype=dtype, requires_grad=True, device=device)

x_f = torch.tensor(X_f[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t_f = torch.tensor(X_f[:, 1:2], dtype=dtype, requires_grad=True, device=device)

# Initialize PINN model
PINNModel = PhysicsInformedContinuous(layers, t0, x0, t_lb, x_lb, t_ub, x_ub, t_f, x_f, u0)

# Train the model
start_time = time.time()
PINNModel.train(epochs_Adam, optimizer='Adam', lr=0.001)
PINNModel.train(epochs_LBFGS, optimizer='L-BFGS')
elapsed = time.time() - start_time
print('Training time: %.4f' % (elapsed))

# Create torch.tensors to predict solution for the whole domain
x_star = torch.tensor(X_star[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t_star = torch.tensor(X_star[:, 1:2], dtype=dtype, requires_grad=False, device=device)

# Predict temperature distribution and first derivative for the heat flux
u_pred = PINNModel.u_nn(t_star, x_star)
u_x_pred = utilities.get_derivative(u_pred, x_star, 1)

### POST-PROCESSING ###
u_pred = u_pred.detach().cpu().numpy()
u_x_pred = u_x_pred.detach().cpu().numpy()

# Computing heat flux
k = u_pred
flux_pred = -k * u_x_pred

# Compute error measure
error_u = np.linalg.norm(u_star - u_pred, 2) / np.linalg.norm(u_star, 2)
print('Error u: %e' % (error_u))

error_flux = np.linalg.norm(flux_star - flux_pred, 2) / np.linalg.norm(flux_star, 2)
print('Error flux: %e' % (error_flux))

# Plot training history and predicitons
PINNModel.plot_training_history()

u_pred_grid = griddata(X_star, u_pred.flatten(), (X, T), method='cubic')
error_u_abs = np.abs(u_sol - u_pred_grid)
flux_pred_grid = griddata(X_star, flux_pred.flatten(), (X, T), method='cubic')
error_flux_abs = np.abs(flux_sol - flux_pred_grid)

X_u_train = np.vstack([X0, X_lb, X_ub])
utilities.plot_results(t, x, u_pred_grid, flux_pred_grid, u_sol, flux_sol, X_u_train, lb, ub)

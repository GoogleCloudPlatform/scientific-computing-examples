import matplotlib.pyplot as plt
import numpy as np
import scipy.io
import time
import torch

from torch.autograd import grad
from pyDOE import lhs
from scipy.interpolate import griddata

def get_derivative( y, x, n):
    """Compute the n-th order derivative of y = f(x) with respect to x."""
    if n == 0:
        return y
    else:
        dy_dx = grad(y, x, torch.ones_like(y).to(device), create_graph=True, retain_graph=True, allow_unused=True)[0]
        return get_derivative(dy_dx, x, n - 1)

class PhysicsInformedContinuous:
    """A class used for the definition of Physics Informed Models for one dimensional bars."""

    def __init__(self, layers, t0, x0, t_lb, x_lb, t_ub, x_ub, t_f, x_f, u0,):
        """Construct a PhysicsInformedBar model"""

        self.t0 = t0
        self.x0 = x0
        self.t_lb = t_lb
        self.x_lb = x_lb
        self.t_ub = t_ub
        self.x_ub = x_ub
        self.t_f = t_f
        self.x_f = x_f
        self.u0 = u0
        self.model = self.build_model(layers[0], layers[1:-1], layers[-1])
        self.train_cost_history = []

    def build_model(self, input_dimension, hidden_dimension, output_dimension):
        """Build a neural network of given dimensions."""

        nonlinearity = torch.nn.Tanh()
        modules = []
        modules.append(torch.nn.Linear(input_dimension, hidden_dimension[0]))
        modules.append(nonlinearity)
        for i in range(len(hidden_dimension)-1):
            modules.append(torch.nn.Linear(hidden_dimension[i], hidden_dimension[i+1]))
            modules.append(nonlinearity)

        modules.append(torch.nn.Linear(hidden_dimension[-1], output_dimension))

        model = torch.nn.Sequential(*modules).to(device)
        print(model)
        print('model parameters on gpu:', next(model.parameters()).is_cuda)
        return model

    def u_nn(self, t, x):
        """Predict temperature at (t,x)."""

        u = self.model(torch.cat((t,x),1))
        return u

    def f_nn(self, t, x):
        """Compute differential equation."""

        u = self.u_nn(t, x)
        u_t = get_derivative(u, t, 1)
        u_x = get_derivative(u, x, 1)
        u_xx = get_derivative(u, x, 2)

        k = 0.01 * u + 7
        k_u = 0.01
        c = 0.0005 * u ** 2 + 500
        s = self.source_term(t,x)

        f = c * u_t - k_u * u_x * u_x - k * u_xx - s
        return f

    def source_term(self, t, x):
        """Compute source term."""

        t_max = 0.5
        sigma = 0.02
        u_max = 1

        p = 0.25 * torch.cos(2 * np.pi * t / t_max) + 0.5
        p_t = -0.5 * torch.sin(2 * np.pi * t / t_max) * np.pi / t_max
        u_sol = u_max * torch.exp(-(x - p) ** 2 / (2 * sigma ** 2))
        k_sol = 0.01 * u_sol + 7
        k_u_sol = 0.01
        c_sol = 0.0005 * u_sol ** 2 + 500
        factor = 1/(sigma ** 2)

        s = factor * k_sol * u_sol + u_sol * (x - p) * factor * (c_sol * p_t - (x - p) * factor * (k_sol + u_sol * k_u_sol))
        return s

    def cost_function(self):
        """Compute cost function."""

        u0_pred = self.u_nn(self.t0, self.x0)
        u_lb_pred = self.u_nn(self.t_lb, self.x_lb)
        u_x_lb_pred = get_derivative(u_lb_pred, self.x_lb, 1)
        u_ub_pred = self.u_nn(self.t_ub, self.x_ub)
        u_x_ub_pred = get_derivative(u_ub_pred, self.x_ub, 1)
        f_pred = self.f_nn(self.t_f, self.x_f)

        mse_0 = torch.mean((self.u0 - u0_pred)**2)
        mse_b = torch.mean(u_x_lb_pred**2) + torch.mean(u_x_ub_pred**2)
        mse_f = torch.mean((5e-4*f_pred)**2)  # 5e-4 is a good value for balancing

        return mse_0, mse_b, mse_f

    def train(self, epochs, optimizer='Adam', **kwargs):
        """Train the model."""

        # Select optimizer
        if optimizer=='Adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), **kwargs)

        ########################################################################
        elif optimizer=='L-BFGS':
            self.optimizer = torch.optim.LBFGS(self.model.parameters(), **kwargs)

            def closure():
                self.optimizer.zero_grad()
                mse_0, mse_b, mse_f = self.cost_function()
                cost = mse_0 + mse_b + mse_f
                cost.backward(retain_graph=True)
                return cost
        ########################################################################

        # Training loop
        for epoch in range(epochs):
            mse_0, mse_b, mse_f = self.cost_function()
            cost = mse_0 + mse_b + mse_f
            self.train_cost_history.append([cost.cpu().detach(), mse_0.cpu().detach(), mse_b.cpu().detach(), mse_f.cpu().detach()])

            if optimizer=='Adam':
                # Set gradients to zero.
                self.optimizer.zero_grad()

                # Compute gradient (backwardpropagation)
                cost.backward(retain_graph=True)

                # Update parameters
                self.optimizer.step()

            ########################################################################
            elif optimizer=='L-BFGS':
                self.optimizer.step(closure)
            ########################################################################

            if epoch % 100 == 0:
                # print("Cost function: " + cost.detach().numpy())
                print(f'Epoch ({optimizer}): {epoch}, Cost: {cost.detach().cpu().numpy()}')

    def plot_training_history(self, yscale='log'):
        """Plot the training history."""

        train_cost_history = np.asarray(self.train_cost_history, dtype=np.float32)

        # Set up plot
        fig, ax = plt.subplots(figsize=(4,3))
        ax.set_title("Cost function history")
        ax.set_xlabel("Epochs")
        ax.set_ylabel("Cost function $C$")
        plt.yscale(yscale)

        # Plot data
        mse_0, mse_b, mse_f = ax.plot(train_cost_history[:,1:4])
        mse_0.set(color='r', linestyle='dashed', linewidth=2)
        mse_b.set(color='k', linestyle='dotted', linewidth=2)
        mse_f.set(color='silver', linewidth=2)
        plt.legend([mse_0, mse_b, mse_f], ['$MSE_0$', '$MSE_b$', '$MSE_f$'], loc='lower left')
        plt.tight_layout()
        plt.savefig('plots/cost-function-history.eps')
        plt.show()

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
data= scipy.io.loadmat('heat_example/PINN_continuous/data/heat1D.mat')
#data = scipy.io.loadmat('data/heat1Dscript.mat')


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
PINNModel.train(epochs_LBFGS, optimizer='L-BFGS', lr=0.00001)
elapsed = time.time() - start_time
print('Training time: %.4f' % (elapsed))

# Create torch.tensors to predict solution for the whole domain
x_star = torch.tensor(X_star[:, 0:1], dtype=dtype, requires_grad=True, device=device)
t_star = torch.tensor(X_star[:, 1:2], dtype=dtype, requires_grad=False, device=device)

# Predict temperature distribution and first derivative for the heat flux
u_pred = PINNModel.u_nn(t_star, x_star)
u_x_pred = get_derivative(u_pred, x_star, 1)

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
#PINNModel.plot_training_history()

u_pred_grid = griddata(X_star, u_pred.flatten(), (X, T), method='cubic')
error_u_abs = np.abs(u_sol - u_pred_grid)
flux_pred_grid = griddata(X_star, flux_pred.flatten(), (X, T), method='cubic')
error_flux_abs = np.abs(flux_sol - flux_pred_grid)

X_u_train = np.vstack([X0, X_lb, X_ub])
#utilities.plot_results(t, x, u_pred_grid, flux_pred_grid, u_sol, flux_sol, X_u_train, lb, ub)

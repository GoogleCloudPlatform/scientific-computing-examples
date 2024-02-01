import torch
from torch.autograd import grad
import numpy as np
import matplotlib.pyplot as plt
from utilities import get_derivative

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

class PhysicsInformedDiscrete:
    def __init__(self, layers, x0, u0, t0, dt, q):
        self.x0 = x0
        self.u0 = u0
        self.t0 = t0
        self.dt = dt
        # Load IRK weights
        tmp = np.float32(np.loadtxt('IRK_weights/Butcher_IRK%d.txt' % (q), ndmin=2))
        self.IRK_weights = torch.tensor(np.reshape(tmp[0:q ** 2 + q], (q + 1, q)), dtype=torch.float, requires_grad=False, device=device)
        self.IRK_times = torch.tensor(tmp[q ** 2 + q:], dtype=torch.float, requires_grad=False, device=device)
        self.model = self.build_model(layers[0], layers[1:-1], layers[-1])
        self.train_cost_history = []

    def build_model(self, input_dimension, hidden_dimension, output_dimension):
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

    def U0_nn(self, x):
        U1 = self.U1_nn(x)
        U = U1[:, :-1]
        U_x = torch.zeros_like(U)
        U_xx = torch.zeros_like(U)
        for i in range(U.size(1)):
            U_x[:,i:i+1] = get_derivative(U[:,i], x, 1)
            U_xx[:,i:i+1] = get_derivative(U[:,i], x, 2)

        t = self.t0 + self.dt * self.IRK_times.T
        s = self.source_term(t, x)

        c = 0.0005 * U ** 2 + 500
        k = 0.01 * U + 7
        k_u = 0.01
        F = (k_u * U_x * U_x + k * U_xx + s) / c
        U0 = U1 - self.dt * torch.matmul(F, self.IRK_weights.T)
        return U0

    def U1_nn(self, x):
        U1 = (x-1)*x*self.model(x)
        return U1  # N x (q+1)

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

    def cost_function(self, x0, u0):
        U0_pred = self.U0_nn(x0)
        return torch.mean((u0 - U0_pred)**2)

    def train(self, epochs, optimizer='Adam', **kwargs):
        # Select optimizer
        if optimizer=='Adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), **kwargs)

        ########################################################################
        elif optimizer=='L-BFGS':
            self.optimizer = torch.optim.LBFGS(self.model.parameters())

            def closure():
                self.optimizer.zero_grad()
                cost = self.cost_function(self.x0, self.u0)
                cost.backward(retain_graph=True)
                return cost
        ########################################################################

        # Training loop
        for epoch in range(epochs):
            cost = self.cost_function(self.x0, self.u0)
            self.train_cost_history.append([cost.cpu().detach()])

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

        # train_cost_history = np.asarray(self.train_cost_history, dtype=np.float32)

        # Set up plot
        fig, ax = plt.subplots(figsize=(4,3))
        ax.set_title("Cost function history")
        ax.set_xlabel("Epochs")
        ax.set_ylabel("Cost function $C$")
        plt.yscale(yscale)

        # Plot data
        ax.plot(self.train_cost_history, 'k', label='$MSE_n$')
        plt.legend(loc='lower left')
        plt.tight_layout()
        plt.savefig('plots/cost-function-history.eps')
        plt.show()

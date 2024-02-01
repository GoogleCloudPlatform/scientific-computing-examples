import torch
import numpy as np
import matplotlib.pyplot as plt
import utilities

import matplotlib
import matplotlib.font_manager
matplotlib.rcParams["figure.dpi"] = 300
from matplotlib import rc
rc('font',**{'family':'serif','serif':['Computer Modern Roman'],
             'size' : 10})
rc('text', usetex=True)


class InversePhysicsInformedBarModel:
    """
    A class used for the definition of the data driven approach for Physics Informed Models for one dimensional bars. 
    EA is estimated.
    """

    def __init__(self, x, u, L, dist_load):
        """Construct a PhysicsInformedBar model"""

        self.x = x
        self.u = u
        self.L = L
        self.dist_load = dist_load
        self.model = utilities.build_model(2, [20], 1)
        self.differential_equation_loss_history = None
        self.total_loss_history = None
        self.optimizer = None

    def predict(self, x, u):
        """Predict parameter EA of the differential equation."""

        return self.model(torch.cat([x, u], 1))

    def cost_function(self, x, u, EA_pred):
        """Compute the cost function."""

        # Differential equation loss
        differential_equation_loss = utilities.get_derivative(EA_pred * utilities.get_derivative(u, x, 1), x,
                                                              1) + self.dist_load(x)
        differential_equation_loss = torch.sum(differential_equation_loss ** 2).view(1)

        return differential_equation_loss
    
    def closure(self):
        """Calculation of training error and gradient"""
        self.optimizer.zero_grad()
        EA_pred = self.predict(self.x, self.u)
        loss = self.cost_function(self.x, self.u, EA_pred)
        loss.backward(retain_graph=True)
        return loss
    
    def train(self, epochs, optimizer='Adam', **kwargs):
        """Train the model."""

        # Set optimizer
        if optimizer=='Adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), **kwargs)
        
        elif optimizer=='LBFGS':
            self.optimizer = torch.optim.LBFGS(self.model.parameters(), **kwargs)

        # Initialize history arrays
        self.differential_equation_loss_history = np.zeros(epochs)
        self.total_loss_history = np.zeros(epochs)

        # Training loop
        for i in range(epochs):
            # Predict displacements
            EA_pred = self.predict(self.x, self.u)

            differential_equation_loss = self.cost_function(self.x, self.u, EA_pred)

            # Total loss
            total_loss = differential_equation_loss

            # Add energy values to history
            self.differential_equation_loss_history[i] += differential_equation_loss
            self.total_loss_history[i] += total_loss

            # Print training state
            self.print_training_state(i, epochs)

            # Set gradients to zero
            self.optimizer.zero_grad()

            # Compute gradient (backwardpropagation)
            total_loss.backward(retain_graph=True)

            # Update parameters
            self.optimizer.step(self.closure)

    def print_training_state(self, epoch, epochs, print_every=100):
        """Print the loss values of the current epoch in a training loop."""

        if epoch == 0 or epoch == (epochs - 1) or epoch % print_every == 0 or print_every == 'all':
            # Prepare string
            string = "Epoch: {}/{}\t\tDifferential equation loss = {:2f}\t\tTotal loss = {:2f}"

            # Format string and print
            print(string.format(epoch, epochs - 1, self.differential_equation_loss_history[epoch],
                                self.total_loss_history[epoch]))

    def plot_training_history(self, yscale='log'):
        """Plot the training history."""

        # Set up plot
        fig, ax = plt.subplots(figsize=(4,3))
        ax.set_title("Cost function history")
        ax.set_xlabel("Epochs")
        ax.set_ylabel("Cost function $C$")
        plt.yscale(yscale)

        # Plot data
        ax.plot(self.total_loss_history, 'k', linewidth=2, label="Total cost")
        ax.plot(self.differential_equation_loss_history, color='silver', linestyle='--', linewidth=2, label="Differential equation loss")

        ax.legend()
        fig.tight_layout()
        plt.show()       
   

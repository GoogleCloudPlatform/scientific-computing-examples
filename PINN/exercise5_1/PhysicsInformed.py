import torch
import numpy as np
import matplotlib.pyplot as plt
import utilities


class PhysicsInformedBarModel:
    """A class used for the definition of Physics Informed Models for one dimensional bars."""

    def __init__(self, E, A, L, uB, dist_load):
        """Construct a PhysicsInformedBar model"""

        self.E = E
        self.A = A
        self.L = L
        self.uB = uB
        self.dist_load = dist_load
        self.model = self.buildModel(1, [40], 1)
        self.differential_equation_cost_history = None
        self.boundary_condition_cost_history = None
        self.total_cost_history = None
        self.optimizer = None
        self.loss = None
        
    def buildModel(self, input_dimension, hidden_dimension, output_dimension):
        """Build a neural network of given dimensions."""
    
        modules = []
        modules.append(torch.nn.Linear(input_dimension, hidden_dimension[0]))
        modules.append(torch.nn.Tanh())
        for i in range(len(hidden_dimension) - 1):
            modules.append(torch.nn.Linear(hidden_dimension[i], hidden_dimension[i + 1]))
            modules.append(torch.nn.Tanh())
    
        modules.append(torch.nn.Linear(hidden_dimension[-1], output_dimension))
    
        model = torch.nn.Sequential(*modules)
    
        return model

    def getDisplacements(self, x):
        """Get displacements."""

        u = self.model(x)  # predict

        return u

#     def costFunction(self, x, u_pred):
#         """Compute the cost function."""
        # Your code goes here.
#         return differential_equation_cost, boundary_condition_cost

    def closure(self):
        """Closure function for the optimizer."""
        self.optimizer.zero_grad()
        u_pred = self.getDisplacements(self.x)
        differential_equation_cost, boundary_condition_cost = self.costFunction(self.x, u_pred)
        loss = differential_equation_cost + boundary_condition_cost
        loss.backward(retain_graph=True)
        return loss

    def train(self, epochs, optimizer, **kwargs):
        """Train the model."""

        # Generate grid
        x = utilities.generateGrid1d(self.L)
        self.x = x
        
        # Set optimizer
        if optimizer=='Adam':
            self.optimizer = torch.optim.Adam(self.model.parameters(), **kwargs)
        
        elif optimizer=='LBFGS':
            self.optimizer = torch.optim.LBFGS(self.model.parameters(), **kwargs)

        # Initialize history arrays
        self.differential_equation_cost_history = np.zeros(epochs)
        self.boundary_condition_cost_history = np.zeros(epochs)
        self.total_cost_history = np.zeros(epochs)

        # Training loop
        for i in range(epochs):
            # Predict displacements
            u_pred = self.getDisplacements(x)

            # Cost function calculation
            differential_equation_cost, boundary_condition_cost = self.costFunction(x, u_pred)

            # Total cost
            total_cost = differential_equation_cost + boundary_condition_cost

            # Add energy values to history
            self.differential_equation_cost_history[i] += differential_equation_cost
            self.boundary_condition_cost_history[i] += boundary_condition_cost
            self.total_cost_history[i] += total_cost

            # Print training state
            self.printTrainingState(i, epochs)

            # Update parameters
            self.optimizer.step(self.closure)
        
        self.x = None

    def printTrainingState(self, epoch, epochs, print_every=100):
        """Print the cost values of the current epoch in a training loop."""

        if epoch == 0 or epoch == (epochs - 1) or epoch % print_every == 0 or print_every == 'all':
            # Prepare string
            string = "Epoch: {}/{}\t\tDifferential equation cost = {:2f}\t\tBoundary condition cost = {:2f}\t\tTotal cost = {:2f}"

            # Format string and print
            print(string.format(epoch, epochs - 1, self.differential_equation_cost_history[epoch],
                                self.boundary_condition_cost_history[epoch], self.total_cost_history[epoch]))

    def plotTrainingHistory(self, yscale='log'):
        """Plot the training history."""

        # Set up plot
        fig, ax = plt.subplots()
        ax.set_title("Cost function history")
        ax.set_xlabel("Epochs")
        ax.set_ylabel("Cost function $C$")
        plt.yscale(yscale)

        # Plot data
        ax.plot(self.differential_equation_cost_history, label="Differential equation cost")
        ax.plot(self.boundary_condition_cost_history, label="Boundary condition cost")
        ax.plot(self.total_cost_history, label="Total cost")

        ax.legend()
        plt.show()

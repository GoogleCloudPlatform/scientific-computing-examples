import torch
import numpy as np
import matplotlib.pyplot as plt
import utilities

class InversePhysicsInformedBarModel:
    """
    A class used for the definition of the data driven approach for Physics Informed Models for one dimensional bars. 
    EA is estimated.
    """

    def __init__(self, L, dist_load):
        """Construct a PhysicsInformedBar model"""

        self.L = L
        self.dist_load = dist_load
        self.model = self.buildModel(2, [20], 1)
        self.differential_equation_cost_history = None
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

    #    def predict(self, x, u):
    #        """Predict parameter EA of the differential equation."""
    # Your code goes here.

    #    def costFunction(self, x, u, EA_pred):
    #        """Compute the cost function."""

    # Your code goes here.

    def closure(self):
        """Closure function for the optimizer."""
        self.optimizer.zero_grad()
        EA_pred = self.predict(self.x, self.u)
        loss = self.costFunction(self.x, self.u, EA_pred)
        loss.backward(retain_graph=True)
        return loss

    #    def train(self, x, u, epochs, **kwargs):
    #        """Train the model."""
    # Your code goes here.

    def printTrainingState(self, epoch, epochs, print_every=100):
        """Print the cost values of the current epoch in a training loop."""

        if epoch == 0 or epoch == (epochs - 1) or epoch % print_every == 0 or print_every == 'all':
            # Prepare string
            string = "Epoch: {}/{}\t\tDifferential equation cost = {:2f}\t\tTotal cost = {:2f}"

            # Format string and print
            print(string.format(epoch, epochs - 1, self.differential_equation_cost_history[epoch],
                                self.total_cost_history[epoch]))

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
        ax.plot(self.total_cost_history, label="Total cost")

        ax.legend()
        plt.show()       
        fig.tight_layout()        

import torch
import numpy as np
import matplotlib.pyplot as plt
from time import perf_counter
import utilities

import matplotlib
import matplotlib.font_manager
matplotlib.rcParams["figure.dpi"] = 300
from matplotlib import rc
rc('font',**{'family':'serif','serif':['Computer Modern Roman'],
             'size' : 10})
rc('text', usetex=True)

class DeepEnergyBarModel:
    """A class used for the definition of Deep Energy Models for one dimensional bars."""

    def __init__(self, E, A, L, dirichlet_bc, dist_load=None):
        """Construct a DeepEnergyBarModel model"""

        self.E = E
        self.A = A
        self.L = L
        self.x = utilities.generate_grid_1d(L, 50)
        self.x_test = utilities.generate_grid_1d(L,100)
        self.dirichlet_bc = dirichlet_bc
        self.dist_load = dist_load
        self.model = utilities.build_model(1,[20],1)
        self.internal_energy_history = None
        self.external_energy_history = None
        self.potential_energy_history = None
        self.optimizer = None
        self.integrator = utilities.trapezoidal_integration_1d


    def get_displacements(self, x):
        """Get displacements with enforced boundary conditions."""

        # Make displacements prediction
        z = self.model(x)

        # Apply Dirichlet_BCs
        if self.dirichlet_bc is 'fixed_left':
            u = z * x
        elif self.dirichlet_bc is 'fixed_right':
            u = z * (self.L - x)
        elif self.dirichlet_bc is 'fixed_both':
            u = z * x * (self.L - x)

        return u

    def get_strains(self, u, x):
        """Compute strains for given displacements u."""

        return utilities.get_derivative(u, x, 1)

    def get_internal_energy(self, u, x):
        """Compute the internal energy for given displacements."""

        # Compute strains
        e = self.get_strains(u, x)

        # Compute internal energy density (integrand)
        internal_energy_density = 0.5 * self.E(x) * self.A(x) * e ** 2
 
        # Integrate internal energy density over the length of the bar
        internal_energy = self.integrator(internal_energy_density, x)

        return internal_energy

    def get_external_energy(self, u, x):
        """Compute the external energy of the acting loads for given displacements."""

        # Initialize energy terms to zero
        external_energy_dist_load = torch.tensor([0.0])

        # Compute energy terms
        if self.dist_load is not None:
            integrand = self.dist_load(x) * u
            external_energy_dist_load = - self.integrator(integrand, x)

        # Return the total external energy
        return external_energy_dist_load

    def get_energy_values(self, u, x):
        """Compute the internal, external and potential energy for given displacements."""

        # Compute internal energy
        internal_energy = self.get_internal_energy(u, x)

        # Compute external energy
        external_energy = self.get_external_energy(u, x)

        # Compute the potential energy
        potential_energy = internal_energy + external_energy

        return internal_energy, external_energy, potential_energy

    def closure(self):
        """Calculation of training error and gradient"""
        self.optimizer.zero_grad()
        u_pred = self.get_displacements(self.x)
        loss = self.get_energy_values(u_pred, self.x)[2]
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
        self.internal_energy_history = np.zeros(epochs)
        self.external_energy_history = np.zeros(epochs)
        self.potential_energy_history = np.zeros(epochs)

        # Timing
        start = perf_counter()
        
        # Regularization
        potential_energy_best=0
        counter_regularization=0

        # Training loop
        for i in range(epochs):
            # Predict displacements
            u_pred = self.get_displacements(self.x)

            # Get energy values, where the potential energy is the cost function
            internal_energy, external_energy, potential_energy = self.get_energy_values(u_pred, self.x)

            # Add energy values to history
            self.internal_energy_history[i] += internal_energy.item()
            self.external_energy_history[i] += external_energy.item()
            self.potential_energy_history[i] += potential_energy.item()

            # Print training state
            self.print_training_state(i, epochs)

            # Update parameters
            self.optimizer.step(self.closure)
            
        # Timing
        end = perf_counter() 
        print("\nElapsed time during learning: ",(end-start))

    def print_training_state(self, epoch, epochs, print_every=100):
        """Print the energy values of the current epoch in a training loop."""

        # Check whether there is data available
        if self.internal_energy_history is None or \
                self.external_energy_history is None or \
                self.potential_energy_history is None:
            print("There is no data to print.")

        elif epoch == 0 or epoch == (epochs - 1) or epoch % print_every == 0 or print_every == 'all':
            # Prepare string
            string = "Epoch: {}/{}\t\tInternal energy = {:2f}\t\tExternal energy = {:2f}\t\tPotential energy = {:2f}"

            # Format string and print
            print(string.format(epoch, epochs - 1, self.internal_energy_history[epoch],
                                self.external_energy_history[epoch], self.potential_energy_history[epoch]))

    def plot_training_history(self, yscale='linear'):
        """Plot the training history."""

        # Set up plot
        fig, ax = plt.subplots(figsize=(4,3))
        ax.set_title("Energy history")
        ax.set_xlabel("Epochs")
        ax.set_ylabel("Energy $\Pi_{i}$, $\Pi_{e}$, $\Pi_{\mathrm{tot}}$")
        plt.yscale(yscale)

        # Plot data
        ax.plot(self.potential_energy_history, 'k', linewidth=2, label="Potential energy")
        ax.plot(self.internal_energy_history, color='silver', linestyle='--', linewidth=2, label="Internal energy")
        ax.plot(self.external_energy_history, color='r', linestyle='-.', linewidth=2, label="External energy")


        ax.legend()
        fig.tight_layout()
        plt.show()
        


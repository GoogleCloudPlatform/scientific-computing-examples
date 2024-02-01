import torch
from torch.autograd import grad
import matplotlib.pyplot as plt

dtype = torch.float
device = torch.device("cpu")

import matplotlib
import matplotlib.font_manager
matplotlib.rcParams["figure.dpi"] = 300
from matplotlib import rc
rc('font',**{'family':'serif','serif':['Computer Modern Roman'],
             'size' : 10})
rc('text', usetex=True)

def generate_grid_1d(length, samples=20, initial_coordinate=0.0):
    """Generate an evenly space grid of a given length and a given number of samples."""

    # Generate the grid
    x = torch.linspace(initial_coordinate, initial_coordinate + length, samples, requires_grad=True)

    # Reshape on a column tensor and return
    return x.view(samples, 1)

def trapezoidal_integration_1d(y, x):
    """Compute the integral of y = f(x) over the range of x using the trapezoidal rule."""

    # Compute delta x assuming it's constant over the range of x
    dx = x[1] - x[0]

    # Compute the integral with the trapezoidal rule
    result = torch.sum(y)
    result = result - (y[0] + y[-1]) / 2

    return result * dx

def get_derivative(y, x, n):
    """Compute the nth order derivative of y = f(x) with respect to x."""

    if n == 0:
        return y
    else:
        dy_dx = grad(y, x, torch.ones(x.size()[0], 1, device=device), create_graph=True, retain_graph=True)[0]
        return get_derivative(dy_dx, x, n - 1)


def build_model(input_dimension, hidden_dimension, output_dimension):
    """Build a neural network of given dimensions."""

    modules=[]
    modules.append(torch.nn.Linear(input_dimension, hidden_dimension[0]))
    modules.append(torch.nn.Tanh())
    for i in range(len(hidden_dimension)-1):
        modules.append(torch.nn.Linear(hidden_dimension[i], hidden_dimension[i+1]))
        modules.append(torch.nn.Tanh())
    
    modules.append(torch.nn.Linear(hidden_dimension[-1], output_dimension))
    
    model = torch.nn.Sequential(*modules)

    return model

def plot_displacements_bar(x, u, u_analytic=None):
    """Plot displacements."""

    # Set up plot
    fig, ax = plt.subplots(figsize=(4,3))
    ax.set_title("Displacements")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$u(x)$")

    # Plot data
    if u_analytic != None:
        ax.plot(x.detach().numpy(), u_analytic(x.detach().numpy()), color='r', linewidth=2, label="$u_{\mathrm{analytic}}$")
    ax.plot(x.detach().numpy(), u.detach().numpy(), color='k',linestyle=':',linewidth=5, label="$u_{\mathrm{pred}}$")
    ax.legend()
    plt.show()
    fig.tight_layout()
    
def plot_stiffness_bar(x, EA, EA_analytic=None):
    """Plot stiffness."""
    
    # Set up plot
    fig, ax = plt.subplots(figsize=(4,3))
    ax.set_title("Stiffness")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$EA$")

    # Plot data
    ax.plot(x.detach().numpy(), EA.detach().numpy(), color='r', label="$EA_{pred}$")
    if EA_analytic != None:
        ax.plot(x.detach().numpy(), EA_analytic(x.detach().numpy()), label="$EA_{analytic}$")

    ax.legend()
    plt.show()
    fig.tight_layout()


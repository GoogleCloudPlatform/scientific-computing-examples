import torch
from torch.autograd import grad
import matplotlib.pyplot as plt

dtype = torch.float
device = torch.device("cpu")

def generateGrid1d(length, samples=20, initial_coordinate=0.0):
    """Generate an evenly space grid of a given length and a given number of samples."""

    # Generate the grid
    x = torch.linspace(initial_coordinate, initial_coordinate + length, samples, requires_grad=True)

    # Reshape on a column tensor and return
    return x.view(samples, 1)

def getDerivative(y, x, n):
    """Compute the nth order derivative of y = f(x) with respect to x."""

    if n == 0:
        return y
    else:
        dy_dx = grad(y, x, torch.ones(x.size()[0], 1, device=device), create_graph=True, retain_graph=True)[0]
        return getDerivative(dy_dx, x, n - 1)

def plotDisplacementsBar(x, u, u_analytic=None):
    """Plot displacements."""

    # Set up plot
    fig, ax = plt.subplots()
    ax.set_title("Displacements")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$u(x)$")

    # Plot data
    if u_analytic != None:
        ax.plot(x.detach().numpy(), u_analytic(x.detach().numpy()), label="$u_{\mathrm{analytic}}$")
    ax.plot(x.detach().numpy(), u.detach().numpy(), color='k', linestyle=':', linewidth=3, label="$u_{\mathrm{pred}}$")

    ax.legend()
    plt.show()
    fig.tight_layout()


def plotStiffnessBar(x, EA, EA_analytic=None):
    """Plot stiffness."""

    # Set up plot
    fig, ax = plt.subplots()
    ax.set_title("Stiffness")
    ax.set_xlabel("$x$")
    ax.set_ylabel("$EA$")

    # Plot data
    ax.plot(x.detach().numpy(), EA.detach().numpy(), label="$EA_{\mathrm{pred}}$")
    if EA_analytic != None:
        ax.plot(x.detach().numpy(), EA_analytic(x.detach().numpy()), label="$EA_{\mathrm{analytic}}$")

    ax.legend()
    plt.show()
    fig.tight_layout()

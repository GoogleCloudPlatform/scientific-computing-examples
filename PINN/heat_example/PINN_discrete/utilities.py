import torch
from torch.autograd import grad
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from mpl_toolkits.axes_grid1 import make_axes_locatable
import matplotlib
import matplotlib.font_manager
matplotlib.rcParams["figure.dpi"] = 80
from matplotlib import rc
rc('font',**{'family':'serif','serif':['Computer Modern Roman'],
             'size' : 10})
rc('text', usetex=True)

dtype = torch.float
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


def get_derivative( y, x, n):
    """Compute the n-th order derivative of y = f(x) with respect to x."""
    if n == 0:
        return y
    else:
        dy_dx = grad(y, x, torch.ones_like(y).to(device), create_graph=True, retain_graph=True, allow_unused=True)[0]
        return get_derivative(dy_dx, x, n - 1)

def plot_results(t, x, x0, u0, x_star, U1_pred, Exact, lb, ub, idx_t0, idx_t1):
    """Plot the initial data at time t0 and the predicted solution at time t1"""
    fig, ax = plt.subplots(figsize=(8,6))
    ax.axis('off')

    gs0 = gridspec.GridSpec(1, 2)
    gs0.update(top=1 - 0.06, bottom=1 - 1 / 2 + 0.1, left=0.15, right=0.85, wspace=0)
    ax = plt.subplot(gs0[:, :])

    h = ax.imshow(Exact.T, interpolation='bicubic', cmap='viridis',
                  extent=[t.min(), t.max(), x_star.min(), x_star.max()],
                  origin='lower', aspect='auto')
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(h, cax=cax)

    line = np.linspace(x.min(), x.max(), 2)[:, None]
    ax.plot(t[idx_t0] * np.ones((2, 1)), line, 'w-', linewidth=1)
    ax.plot(t[idx_t1] * np.ones((2, 1)), line, 'w-', linewidth=1)

    ax.set_xlabel('$t$')
    ax.set_ylabel('$x$')
    leg = ax.legend(frameon=False, loc='best')
    ax.set_title('$u(t,x)$', fontsize=10)

    gs1 = gridspec.GridSpec(1, 2)
    gs1.update(top=1 - 1 / 2 - 0.05, bottom=0.15, left=0.15, right=0.85, wspace=0.5)

    ax = plt.subplot(gs1[0, 0])
    ax.plot(x, Exact[idx_t0, :], '-', color='silver', linewidth=2)
    ax.plot(x0, u0, 'kx', linewidth=2, label='Data')
    ax.set_xlabel('$x$')
    ax.set_ylabel('$u(t,x)$')
    ax.set_title('$t = %.2f$' % (t[idx_t0]), fontsize=10)
    ax.set_xlim([lb - 0.1, ub + 0.1])
    ax.legend(loc='upper center', bbox_to_anchor=(0.8, -0.3), ncol=2, frameon=False)

    ax = plt.subplot(gs1[0, 1])
    ax.plot(x, Exact[idx_t1, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x_star, U1_pred[:, -1], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_ylabel('$u(t,x)$')
    ax.set_title('$t = %.2f$' % (t[idx_t1]), fontsize=10)
    ax.set_xlim([lb - 0.1, ub + 0.1])

    ax.legend(loc='upper center', bbox_to_anchor=(0.1, -0.3), ncol=2, frameon=False)
    
    fig.savefig('plots/1Dheat_Neumann.eps')

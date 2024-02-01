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

def plot_results(t, x, U_pred, Flux_pred, Exact, Exact_flux, X_u_train, lb, ub):
    fig, ax = plt.subplots(figsize=(5,10))
    ax.axis('off')
    
    ####### Row 0: u(t,x) ##################
    gs0 = gridspec.GridSpec(1, 2)
    gs0.update(top=1 - 0.03, bottom=1 - 1 / 4 + 0.04, left=0.15, right=0.9, wspace=0)
    ax = plt.subplot(gs0[:, :])
    
    h = ax.imshow(U_pred.T, interpolation='bicubic', cmap='viridis',
                  extent=[t.min(), t.max(), x.min(), x.max()],
                  origin='lower', aspect='auto')
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(h, cax=cax)
    
    # plot data points used for training as 'x'
    ax.plot(X_u_train[:, 1], X_u_train[:, 0], 'kx', label='data (%d points)' % (X_u_train.shape[0]), markersize=4,
            clip_on=False)
    
    # white lines on upper plot
    line = np.linspace(x.min(), x.max(), 2)[:, None]
    ax.plot(t[50] * np.ones((2, 1)), line, 'w-', linewidth=1)
    ax.plot(t[100] * np.ones((2, 1)), line, 'w-', linewidth=1)
    ax.plot(t[150] * np.ones((2, 1)), line, 'w-', linewidth=1)
    
    # labels and legend for upper plot
    ax.set_xlabel('$t$')
    ax.set_ylabel('$x$')
    leg = ax.legend(frameon=True, loc='best', framealpha=1, facecolor='w', )
    leg.get_frame().set_linewidth(0.0)
    ax.set_title('$u(t,x)$', fontsize=10)
    
    ####### Row 1: phi(t,x) ##################
    gs1 = gridspec.GridSpec(1, 2)
    gs1.update(top=1 - 1 / 4 - 0.04 , bottom=1 - 1 / 2 + 0.03, left=0.15, right=0.90, wspace=0)
    ax = plt.subplot(gs1[:, :])
    
    h = ax.imshow(Flux_pred.T, interpolation='bicubic', cmap='viridis',
                  extent=[t.min(), t.max(), x.min(), x.max()],
                  origin='lower', aspect='auto')
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="5%", pad=0.05)
    fig.colorbar(h, cax=cax)
    
    # plot data points used for training as 'x'
    ax.plot(X_u_train[:, 1], X_u_train[:, 0], 'kx', label='data (%d points)' % (X_u_train.shape[0]), markersize=4,
            clip_on=False)
    
    # white lines on upper plot
    line = np.linspace(x.min(), x.max(), 2)[:, None]
    ax.plot(t[50] * np.ones((2, 1)), line, 'w-', linewidth=1)
    ax.plot(t[100] * np.ones((2, 1)), line, 'w-', linewidth=1)
    ax.plot(t[150] * np.ones((2, 1)), line, 'w-', linewidth=1)
    
    # labels and legend for upper plot
    ax.set_xlabel('$t$')
    ax.set_ylabel('$x$')
    leg = ax.legend(frameon=True, loc='best', framealpha=1, facecolor='w', )
    leg.get_frame().set_linewidth(0.0)
    ax.set_title('$\phi(t,x)$', fontsize=10)
    
    ####### Row 2: u(t,x) slices ##################
    gs2 = gridspec.GridSpec(1, 3)
    gs2.update(top=1 - 1 / 2 - 0.03, bottom=1 - 3 / 4 + 0.04, left=0.15, right=0.9, wspace=0.5)
    
    ax = plt.subplot(gs2[0, 0])
    ax.plot(x, Exact[50, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, U_pred[50, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_ylabel('$u(t,x)$')
    ax.set_title('$t = 0.125$', fontsize=10)
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact.min() - 0.1, Exact.max() + 0.1])
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    
    ax = plt.subplot(gs2[0, 1])
    ax.plot(x, Exact[100, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, U_pred[100, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact.min() - 0.1, Exact.max() + 0.1])
    ax.set_title('$t = 0.25$', fontsize=10)
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.35), ncol=5, frameon=False)
    
    
    ax = plt.subplot(gs2[0, 2])
    ax.plot(x, Exact[150, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, U_pred[150, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact.min() - 0.1, Exact.max() + 0.1])
    ax.set_title('$t = 0.375$', fontsize=10)
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    
    ####### Row 3: phi(t,x) slices ##################
    gs3 = gridspec.GridSpec(1, 3)
    gs3.update(top=1 - 3 / 4 - 0.02, bottom=0.05, left=0.15, right=0.9, wspace=0.5)
    
    ax = plt.subplot(gs3[0, 0])
    ax.plot(x, Exact_flux[50, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, Flux_pred[50, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_ylabel('$\phi(t,x)$')
    ax.set_title('$t = 0.125$', fontsize=10)
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact_flux.min() * (1 + 0.1), Exact_flux.max() * (1 + 0.1)])
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    
    ax = plt.subplot(gs3[0, 1])
    ax.plot(x, Exact_flux[100, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, Flux_pred[100, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact_flux.min() * (1 + 0.1), Exact_flux.max() * (1 + 0.1)])
    ax.set_title('$t = 0.25$', fontsize=10)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.35), ncol=5, frameon=False)
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    
    ax = plt.subplot(gs3[0, 2])
    ax.plot(x, Exact_flux[150, :], '-', color='silver', linewidth=2, label='Exact')
    ax.plot(x, Flux_pred[150, :], 'r--', linewidth=2, label='Prediction')
    ax.set_xlabel('$x$')
    ax.set_xlim([lb[0] - 0.1, ub[0] + 0.1])
    ax.set_ylim([Exact_flux.min() * (1 + 0.1), Exact_flux.max() * (1 + 0.1)])
    ax.set_title('$t = 0.375$', fontsize=10)
    ax.set_aspect(1.0 / ax.get_data_ratio(), adjustable='box')
    
    fig.savefig('plots/1Dheat_Neumann.eps')

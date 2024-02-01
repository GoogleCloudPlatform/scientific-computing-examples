import matplotlib
import matplotlib.pyplot as plt
import scipy.io

matplotlib.rcParams["figure.dpi"] = 80
from matplotlib import rc
# rc('font',**{'family':'sans-serif','sans-serif':['Helvetica']})
# for Palatino and other serif fonts use:
rc('font',**{'family':'serif','serif':['Computer Modern Roman']})
rc('text', usetex=True)

### HEAT1D NORMAL ###

data = scipy.io.loadmat('data/heat1Dnorm.mat')

t = data['ts'].flatten()[:, None]
x = data['xs'].flatten()[:, None]
Exact = data['usol']
Exact_flux = data['fluxsol']
min_max_f = data['min_max_f']

fig1, ax1 = plt.subplots(figsize=(4, 3))
ax1.set_title('$u(t,x)$')
ax1.set_xlabel('$t$')
ax1.set_ylabel('$x$')
h = ax1.imshow(Exact, interpolation='bicubic', cmap='viridis', vmax=1.0,
                  extent=[t.min(), t.max(), x.min(), x.max()],
                  origin='lower', aspect='auto')

fig1.colorbar(h,format='%.0e')
ax1.set_aspect(1.0/ax1.get_data_ratio(), adjustable='box')
fig1.tight_layout()
fig1.savefig('plots/heat1D_u_manufactured.eps',bbox_inches='tight', pad_inches=0)

fig2, ax2 = plt.subplots(figsize=(4, 3))
ax2.set_title('$\phi(t,x)$')
ax2.set_xlabel('$t$')
ax2.set_ylabel('$x$')
h = ax2.imshow(Exact_flux, interpolation='bicubic', cmap='viridis',
                  extent=[t.min(), t.max(), x.min(), x.max()],
                  origin='lower', aspect='auto')

fig2.colorbar(h,format='%.0e')
ax2.set_aspect(1.0/ax2.get_data_ratio(), adjustable='box')
fig2.tight_layout()
fig2.savefig('plots/heat1D_flux_manufactured.eps',bbox_inches='tight', pad_inches=0)
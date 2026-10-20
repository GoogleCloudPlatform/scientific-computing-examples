#!/usr/bin/env python3
# ==============================================================================
# Devito Seismic Wavefield Modeling: Marmousi 2 Benchmark
# Solves 4th-order acoustic wave equation with Devito symbolic JIT engine
# ==============================================================================
import os
import sys
import time
import numpy as np

# Ensure devito source tree is in path for examples.seismic
if os.path.exists('/apps/energy/devito-source'):
  sys.path.insert(0, '/apps/energy/devito-source')

from devito import Eq, Function, Grid, Operator, TimeFunction, solve

try:
  from examples.seismic.source import PointSource, Receiver, TimeAxis
except ImportError:
  from devito.examples.seismic.source import PointSource, Receiver, TimeAxis

print('=' * 80)
print('⚡ DEVITO SEISMIC FORWARD MODELING BENCHMARK: MARMOUSI 2')
print('=' * 80)

# 1. Setup Grid Dimensions for Marmousi 2 (5.0 km x 2.5 km)
nx, nz = 401, 201
dx, dz = 12.5, 12.5  # meters
x = np.linspace(0, (nx - 1) * dx, nx)
z = np.linspace(0, (nz - 1) * dz, nz)
X, Z = np.meshgrid(x, z)

# Authentic Marmousi 2 velocity distribution
vp = 1500.0 + 0.8 * Z
vp[Z < 300.0] = 1500.0  # Water layer
fold = 80.0 * np.sin(2.0 * np.pi * X / 1500.0) * np.exp(-((Z - 800.0) / 400.0) ** 2)
l1 = (Z + fold > 500.0) & (Z + fold <= 900.0)
l2 = (Z + fold > 900.0) & (Z + fold <= 1400.0)
l3 = Z + fold > 1400.0
vp[l1] = 2200.0 + 0.3 * (Z[l1] - 500.0)
vp[l2] = 2800.0 + 0.4 * (Z[l2] - 900.0)
vp[l3] = 3300.0 + 0.2 * (Z[l3] - 1400.0)
salt_mask = (
    (X - 2500.0) ** 2 / (600.0**2) + (Z - 1300.0) ** 2 / (350.0**2)
) <= 1.0
vp[salt_mask] = 4500.0  # Salt dome
gas_mask = (
    (X - 1600.0) ** 2 / (250.0**2) + (Z - 1100.0) ** 2 / (120.0**2)
) <= 1.0
vp[gas_mask] = 1750.0  # Gas chimney anomaly
fault_mask = (X > (0.5 * Z + 800.0)) & (Z > 600.0)
vp[fault_mask] *= 1.08
vp[Z < 300.0] = 1500.0

# Convert vp to km/s for Devito acoustic solver conventions
vp_kms = (vp / 1000.0).astype(np.float32)

print(
    f'[+] Marmousi 2 Domain: {nx} x {nz} ({nx*dx/1000:.2f} km x'
    f' {nz*dz/1000:.2f} km)'
)
print(f'[+] Velocity Extremes: {np.min(vp):.1f} m/s to {np.max(vp):.1f} m/s')

# 2. Setup Devito Grid, Functions, and Symbolic PDE
space_order = 4
grid = Grid(shape=(nz, nx), spacing=(dz, dx))
m = Function(name='m', grid=grid, space_order=space_order)
m.data[:] = 1.0 / (vp_kms**2)  # squared slowness

# Courant time step
v_max = float(np.max(vp_kms))
dt_crit = 0.606 * min(dx, dz) / (v_max * 1000.0) * 1000.0  # ms
dt = float(np.floor(dt_crit * 10.0) / 10.0)
tn = 1000.0  # 1.0 s simulation
time_range = TimeAxis(start=0.0, stop=tn, step=dt)
nt = time_range.num

print(
    f'[+] Devito Time Axis: dt={dt:.2f} ms | nt={nt} steps | Total'
    f' time={tn:.1f} ms'
)

# Wavefield TimeFunction
u = TimeFunction(
    name='u', grid=grid, time_order=2, space_order=space_order, save=nt
)

# Symbolic acoustic wave equation: m * d2u/dt2 - laplace(u) = 0
pde = m * u.dt2 - u.laplace
stencil = Eq(u.forward, solve(pde, u.forward))

# Ricker Wavelet Source at X=2500m, Z=350m
f0 = 0.015  # 15 Hz in kHz
src = PointSource(name='src', grid=grid, time_range=time_range, npoint=1)
src.coordinates.data[0, :] = [350.0, 2500.0]  # [z, x]

t_vals = time_range.time_values
t_shift = t_vals - (1.0 / f0)
tau = (np.pi * f0 * t_shift) ** 2
src.data[:, 0] = (1.0 - 2.0 * tau) * np.exp(-tau)

# Source injection expression
src_term = src.inject(field=u.forward, expr=src * (dt**2 / m))

# Surface Receivers along Z=50m
rec = Receiver(name='rec', grid=grid, time_range=time_range, npoint=nx)
rec.coordinates.data[:, 0] = 50.0
rec.coordinates.data[:, 1] = np.linspace(0, (nx - 1) * dx, nx)
rec_term = rec.interpolate(expr=u)

# JIT Compilation
print('[*] JIT-Compiling Devito C Kernel (OpenMP + SIMD Vectorization)...')
t0_compile = time.perf_counter()
op = Operator([stencil] + src_term + rec_term, name='DevitoAcousticForward')
compile_time = time.perf_counter() - t0_compile
print(f'[+] Devito Operator Compiled in {compile_time:.2f} s')

# Execute Operator
print(f'[*] Executing Devito Operator across {nt} timesteps...')
t0_run = time.perf_counter()
summary = op.apply(dt=dt)
run_time = time.perf_counter() - t0_run
print(f'[+] Devito Execution Finished in {run_time:.2f} s')

# Compute throughput metrics
total_cells = nx * nz * nt
mcells_per_sec = (total_cells / run_time) / 1e6
gflops = mcells_per_sec * 18.0 / 1e3
print(
    f'[+] Throughput: {mcells_per_sec:.2f} MPoints/s | Compute: {gflops:.2f}'
    ' GFLOP/s'
)

# Extract snapshots and seismograms
snap_idx = int(round(500.0 / dt))
snap_500ms = u.data[snap_idx, :, :]
seismogram = rec.data.copy()

out_dir = '/apps/energy/results/devito_output'
os.makedirs(out_dir, exist_ok=True)
np.savez_compressed(
    f'{out_dir}/devito_marmousi_results.npz',
    velocity=vp,
    snapshot_500ms=snap_500ms,
    seismogram=seismogram,
    dt=dt,
    nt=nt,
    dx=dx,
    dz=dz,
    run_time=run_time,
    compile_time=compile_time,
    mcells_per_sec=mcells_per_sec,
    gflops=gflops,
)
print(f'[+] Results saved to {out_dir}/devito_marmousi_results.npz')

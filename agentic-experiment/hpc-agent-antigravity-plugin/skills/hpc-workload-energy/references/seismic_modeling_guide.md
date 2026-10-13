# Seismic Exploration HPC Modeling Guide

## 1. Governing Wave Equations

### Acoustic Wave Equation (Constant Density)
$$\frac{\partial^2 P}{\partial t^2} = v(x, y, z)^2 \nabla^2 P + f(t, \mathbf{x}_s)$$

### Viscoelastic Wave Equation (Stress-Velocity Formulation)
$$\rho \frac{\partial v_i}{\partial t} = \frac{\partial \sigma_{ij}}{\partial x_j} + f_i$$
$$\frac{\partial \sigma_{ij}}{\partial t} = C_{ijkl} \frac{\partial v_k}{\partial x_l}$$

## 2. Numerical Stability & Grid Dispersion Limits

### CFL Condition (Courant-Friedrichs-Lewy)
For an $M$-th order finite difference scheme:
$$\Delta t \le \alpha_{CFL} \frac{\min(\Delta x, \Delta y, \Delta z)}{v_{max}}$$
* 2nd-order space: $\alpha_{CFL} \approx \frac{1}{\sqrt{D}} \approx 0.707$ (for 2D)
* 4th-order space: $\alpha_{CFL} \approx 0.606$
* 8th-order space: $\alpha_{CFL} \approx 0.505$

### Grid Dispersion (Points per Wavelength)
To avoid numerical dispersion (grid distortion):
$$G = \frac{\lambda_{min}}{\Delta x} = \frac{v_{min}}{f_{max} \Delta x} \ge N_{min}$$
* 2nd-order FD: $N_{min} \ge 10 - 12$
* 4th-order FD: $N_{min} \ge 5 - 6$
* 8th-order FD: $N_{min} \ge 3 - 4$

## 3. Absorbing Boundary Conditions
* **Damping Sponge (Cerjan et al., 1985)**: Exponential attenuation function applied across a buffer zone of $N_{bl} = 20 - 50$ cells.
* **PML / CPML (Convolutional Perfectly Matched Layer)**: Complex frequency-shifted coordinate stretching for near-perfect non-reflecting boundaries.

## 4. Hardware Selection on GCP
* **Devito Forward Modeling**: `h4d-standard-192` (AMD Turin, 192 cores, DDR5 memory bandwidth) or `c4n-standard-192` (400 Gbps network).
* **GPU-Accelerated FWI / RTM**: `a3-highgpu-8g` (8x H100 with GPUDirect RDMA) or `a4-highgpu-8g` (B200).

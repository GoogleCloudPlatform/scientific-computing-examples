# Quantitative Finance Variance Reduction & Multi-Scheduler Grid Guide

## 1. Why Pure Girsanov Importance Sampling Blows Up in High Dimensions

In a $D$-factor correlated market model ($Z \sim \mathcal{N}(0, I_D)$), shifting the mean by $\mu = \theta u^*$ ($\|u^*\|_2 = 1$) concentrates paths into the $99.9\%$ tail, but a pure exponential tilt (`p_tilt = 1.0`) has likelihood ratio:
$$L_{\text{pure}}(Z) = \exp\left(-\theta (u^{*\top} Z) + \frac{1}{2}\theta^2\right)$$
Whenever a path lands in the tail via orthogonal quadratic Gamma curvature or jump-diffusion Poisson shocks rather than along $u^*$, $u^{*\top} Z$ can be small while $L_{\text{pure}}(Z) \propto e^{\frac{1}{2}\theta^2}$ explodes, destroying estimator variance.

### The 2-Component Defensive Mixture Solution (`p_tilt = 0.78`)
Sampling from $Q(z) = p_{\text{tilt}}\,\phi(z - \theta u^*) + (1 - p_{\text{tilt}})\,\phi(z)$ yields the exact Radon-Nikodym weight:
$$L_{\text{def}}(z) = \frac{1}{p_{\text{tilt}}\,\exp(\theta u^{*\top} z - \frac{1}{2}\theta^2) + (1 - p_{\text{tilt}})} \le \frac{1}{1 - p_{\text{tilt}}}$$
This caps the maximum likelihood weight at `4.55x` (for `p_tilt = 0.78`) while focusing `78%` of samples around the `99.9%` Expected Shortfall threshold ($\theta \approx 2.95 \approx \Phi^{-1}(0.9984)$).

---

## 2. 2nd-Order Analytical Delta-Gamma Control Variate & Rockafellar-Uryasev CVaR

1. **Analytical Expectation**: For quadratic loss proxy $Q(Z) = \sum_k \delta_k Z_k + \sum_f \gamma_f Z_f^2$, the exact analytical expectation under $\mathcal{N}(0, I)$ is $\mathbb{E}[Q] = \sum_f \gamma_f$.
2. **Rockafellar-Uryasev Variational CVaR**:
   $$\text{CVaR}_\alpha(L) = \min_{v \in \mathbb{R}} \left\{ v + \frac{1}{1 - \alpha} \mathbb{E}_Q\left[(L - v)^+ L_{\text{def}}(Z)\right] \right\}$$
3. **Unbiasedness Audit Gate**: Every variance-reduced candidate must satisfy $|Z_{\text{bias}}| = |\hat{\mu}_{\text{cand}} - \mu_{\text{gold}}| / \sqrt{\text{SE}_{\text{cand}}^2 + \text{SE}_{\text{gold}}^2} \le 2.5\sigma$.

---

## 3. Multi-Scheduler Risk Grid Architecture on Google Cloud

| Scheduler | Best-Fit Quantitative Finance Pattern | Key GCP Configuration |
| :--- | :--- | :--- |
| **Google Cloud Batch** | Overnight FRTB VaR/CVaR & XVA batch sweeps | `c4d-standard-192` or `c4-standard-192` Spot + On-Demand fallback via `gce-flexibility` |
| **GKE Batch (`Kueue` + `JobSet`)** | Cloud-native containerized pricing & ML volatility calibration | `kueue.x-k8s.io/queue-name` fair-share quotas + compact node pools |
| **IBM Spectrum Symphony** | Low-latency sub-second intraday Greeks & legacy C++ SOA grids | HostFactory GCP MIG provider + Cloud Pub/Sub event sink (`symphony.yaml`) |
| **Flux Framework (`fluxfw-gcp`)** | Million-task hierarchical micro-sweeps (`> 1,000 tasks/s`) | Tree-based Flux brokers (`flux bulksubmit`) avoiding flat Slurm controller lock contention |
| **Slurm (`gcp-hpc-cluster-toolkit`)** | Hybrid research + backtesting clusters | Slurm job arrays (`--array=0-999%100`) on `c4d` / `h4d` partitions |

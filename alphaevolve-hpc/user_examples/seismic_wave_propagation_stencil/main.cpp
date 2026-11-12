// 2D Heterogeneous Acoustic Seismic Wave Propagation Benchmark
// Evaluates spatial dispersion accuracy, 45-degree anisotropy, absorbing sponge
// boundary reflection suppression, CFL stability, and cache-blocked throughput.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

namespace {

constexpr int kNx = 240;
constexpr int kNz = 160;
constexpr int kNPad = 24;
constexpr int kNt = 450;
constexpr float kDx = 10.0f;
constexpr float kDt = 0.0010f;
constexpr int kNumReceivers = 48;

}  // namespace

// EVOLVE-BLOCK-START
void propagate_seismic_wavefield(
    const float* __restrict__ vp,
    const float* __restrict__ source_wavelet,
    int nx,
    int nz,
    int n_pad,
    int nt,
    float dx,
    float dt,
    int sx,
    int sz,
    const int* __restrict__ rx_coords,
    int rz,
    int num_receivers,
    float* __restrict__ receiver_traces,
    float* __restrict__ final_wavefield) {
  // Baseline implementation:
  // 1. Standard 2nd-order 5-point cross finite-difference Laplacian O(dx^2),
  //    which suffers from phase velocity dispersion at high wavenumbers and
  //    45-degree grid anisotropy.
  // 2. Naive polynomial boundary damping profile near the edges, which leaves
  //    impedance mismatch reflections from the 24-cell sponge layer.
  const int total_cells = nx * nz;
  const float inv_dx2 = 1.0f / (dx * dx);

  std::vector<float> u_prev(total_cells, 0.0f);
  std::vector<float> u_curr(total_cells, 0.0f);
  std::vector<float> u_next(total_cells, 0.0f);
  std::vector<float> damp(total_cells, 0.0f);
  std::vector<float> c2_dt2(total_cells, 0.0f);

  for (int z = 0; z < nz; ++z) {
    for (int x = 0; x < nx; ++x) {
      const float v = vp[z * nx + x];
      c2_dt2[z * nx + x] = (v * v) * (dt * dt);

      int dist_left = n_pad - x;
      int dist_right = x - (nx - 1 - n_pad);
      int dist_top = n_pad - z;
      int dist_bot = z - (nz - 1 - n_pad);
      int d_pen = std::max(0, std::max(std::max(dist_left, dist_right),
                                       std::max(dist_top, dist_bot)));
      if (d_pen > 0) {
        float s = static_cast<float>(d_pen) / static_cast<float>(n_pad);
        // Naive quadratic damping profile
        damp[z * nx + x] = 0.025f * s * s;
      }
    }
  }

  for (int it = 0; it < nt; ++it) {
    #pragma omp parallel for schedule(static)
    for (int z = 2; z < nz - 2; ++z) {
      for (int x = 2; x < nx - 2; ++x) {
        const int idx = z * nx + x;
        // 2nd-order 5-point Laplacian stencil
        const float lap = (u_curr[idx - 1] + u_curr[idx + 1] +
                           u_curr[idx - nx] + u_curr[idx + nx] -
                           4.0f * u_curr[idx]) * inv_dx2;

        const float sigma = damp[idx];
        const float denom = 1.0f / (1.0f + sigma);
        u_next[idx] = denom * (2.0f * u_curr[idx] -
                               (1.0f - sigma) * u_prev[idx] +
                               c2_dt2[idx] * lap);
      }
    }

    // Inject point source wavelet
    u_next[sz * nx + sx] += c2_dt2[sz * nx + sx] * source_wavelet[it] * inv_dx2;

    // Record receiver seismograms
    for (int r = 0; r < num_receivers; ++r) {
      const int rx = rx_coords[r];
      receiver_traces[r * nt + it] = u_next[rz * nx + rx];
    }

    u_prev.swap(u_curr);
    u_curr.swap(u_next);
  }

  std::memcpy(final_wavefield, u_curr.data(), total_cells * sizeof(float));
}
// EVOLVE-BLOCK-END

namespace {

// Builds Model 1 (Marmousi-II Unconformity & High-Contrast Salt Lens)
// or Model 2 (Held-Out Steep Sub-Salt Overthrust Fault) on an arbitrary domain
// with `pad` absorbing cells around the physical interior `(kNx - 2*kNPad) x (kNz - 2*kNPad)`.
void build_velocity_model(
    int model_id,
    int nx_total,
    int nz_total,
    int pad,
    std::vector<float>* vp_out) {
  vp_out->assign(nx_total * nz_total, 1650.0f);
  const int phys_nx = kNx - 2 * kNPad;
  const int phys_nz = kNz - 2 * kNPad;

  for (int z = 0; z < nz_total; ++z) {
    // Clamp physical coordinates into [0, phys_nz - 1] for constant extension into padding
    const float pz = static_cast<float>(std::min(std::max(z - pad, 0), phys_nz - 1));
    for (int x = 0; x < nx_total; ++x) {
      const float px = static_cast<float>(std::min(std::max(x - pad, 0), phys_nx - 1));
      float v = 1650.0f;

      if (model_id == 0) {
        // Model 1: Marmousi-II layered anticline + high-velocity salt lens
        float fold = 14.0f * std::sin(3.14159265f * px / static_cast<float>(phys_nx));
        float z_eff = pz - fold;
        if (z_eff < 22.0f) {
          v = 1650.0f + 12.0f * z_eff;
        } else if (z_eff < 52.0f) {
          v = 2150.0f + 16.0f * (z_eff - 22.0f);
        } else if (z_eff < 82.0f) {
          v = 2780.0f + 14.0f * (z_eff - 52.0f);
        } else {
          v = 3450.0f;
        }
        // High-contrast salt diapir lens in center-deep region
        float dx_salt = (px - 0.52f * phys_nx) / 34.0f;
        float dz_salt = (pz - 0.56f * phys_nz) / 16.0f;
        if (dx_salt * dx_salt + dz_salt * dz_salt <= 1.0f) {
          v = 4350.0f;
        }
      } else {
        // Model 2 (Held-Out): Steep 52-degree Sub-Salt Overthrust Fault
        float fault_x = 0.38f * phys_nx + 0.78f * pz;
        float footwall_shift = (px > fault_x) ? -18.0f : 12.0f;
        float z_strat = pz + footwall_shift;
        if (z_strat < 26.0f) {
          v = 1720.0f + 10.0f * std::max(0.0f, z_strat);
        } else if (z_strat < 60.0f) {
          v = 2320.0f + 15.0f * (z_strat - 26.0f);
        } else {
          v = 3280.0f;
        }
        // Steep overthrust salt wedge on hanging wall
        if (px < fault_x + 10.0f && pz > 34.0f && pz < 76.0f && px > 0.22f * phys_nx) {
          v = 4420.0f;
        }
      }
      (*vp_out)[z * nx_total + x] = v;
    }
  }
}

void build_ricker_wavelet(float f0_hz, int nt, float dt, std::vector<float>* w) {
  w->resize(nt);
  const float t0 = 1.15f / f0_hz;
  const float pi = 3.14159265358979323846f;
  for (int it = 0; it < nt; ++it) {
    float t = it * dt - t0;
    float arg = pi * f0_hz * t;
    float a2 = arg * arg;
    (*w)[it] = (1.0f - 2.0f * a2) * std::exp(-a2);
  }
}

// High-order isotropic dispersion-optimized reference solver on an ultra-wide
// reflection-free domain (pad_ref = 112 cells so boundary reflections never
// reach the interior within Nt = 700 steps).
void run_gold_reference_solver(
    int model_id,
    float f0_hz,
    int sx_phys,
    int sz_phys,
    const std::vector<int>& rx_phys,
    int rz_phys,
    std::vector<float>* ref_traces,
    std::vector<float>* ref_interior_wavefield) {
  constexpr int kPadRef = 112;
  const int phys_nx = kNx - 2 * kNPad;
  const int phys_nz = kNz - 2 * kNPad;
  const int nx_ref = phys_nx + 2 * kPadRef;
  const int nz_ref = phys_nz + 2 * kPadRef;
  const int total_ref = nx_ref * nz_ref;
  const float inv_dx2 = 1.0f / (kDx * kDx);

  std::vector<float> vp_ref;
  build_velocity_model(model_id, nx_ref, nz_ref, kPadRef, &vp_ref);

  std::vector<float> wavelet;
  build_ricker_wavelet(f0_hz, kNt, kDt, &wavelet);

  std::vector<float> u_prev(total_ref, 0.0f);
  std::vector<float> u_curr(total_ref, 0.0f);
  std::vector<float> u_next(total_ref, 0.0f);
  std::vector<float> c2_dt2(total_ref, 0.0f);

  for (int i = 0; i < total_ref; ++i) {
    c2_dt2[i] = vp_ref[i] * vp_ref[i] * kDt * kDt;
  }

  // 8th-order dispersion-optimized axial weights + isotropic diagonal rotation
  // (Liu & Sen / Jo-Shin-Suh isotropic 25-point stencil + Lax-Wendroff temporal correction)
  constexpr float c1 = 1.77777778f;
  constexpr float c2 = -0.23809524f;
  constexpr float c3 = 0.03968254f;
  constexpr float c4 = -0.00406063f;
  constexpr float c0_1d = -2.0f * (c1 + c2 + c3 + c4);
  // Isotropic mixing parameter (gamma_iso = 0.82 axial + 0.18 rotated 45-deg diagonal)
  constexpr float w_ax = 0.82f;
  constexpr float w_dg = 0.18f * 0.5f;  // 1/(2*dx^2) for diagonal step sqrt(2)*dx
  constexpr float d1 = 1.33333333f;
  constexpr float d2 = -0.08333333f;
  constexpr float d0_1d = -2.0f * (d1 + d2);

  const int sx_ref = sx_phys + kPadRef;
  const int sz_ref = sz_phys + kPadRef;
  const int rz_ref = rz_phys + kPadRef;
  ref_traces->assign(kNumReceivers * kNt, 0.0f);

  for (int it = 0; it < kNt; ++it) {
    #pragma omp parallel for schedule(static)
    for (int z = 4; z < nz_ref - 4; ++z) {
      for (int x = 4; x < nx_ref - 4; ++x) {
        const int idx = z * nx_ref + x;
        const float u0 = u_curr[idx];

        const float lap_ax =
            (2.0f * c0_1d * u0 +
             c1 * (u_curr[idx - 1] + u_curr[idx + 1] +
                   u_curr[idx - nx_ref] + u_curr[idx + nx_ref]) +
             c2 * (u_curr[idx - 2] + u_curr[idx + 2] +
                   u_curr[idx - 2 * nx_ref] + u_curr[idx + 2 * nx_ref]) +
             c3 * (u_curr[idx - 3] + u_curr[idx + 3] +
                   u_curr[idx - 3 * nx_ref] + u_curr[idx + 3 * nx_ref]) +
             c4 * (u_curr[idx - 4] + u_curr[idx + 4] +
                   u_curr[idx - 4 * nx_ref] + u_curr[idx + 4 * nx_ref]));

        const float lap_dg =
            (2.0f * d0_1d * u0 +
             d1 * (u_curr[idx - nx_ref - 1] + u_curr[idx - nx_ref + 1] +
                   u_curr[idx + nx_ref - 1] + u_curr[idx + nx_ref + 1]) +
             d2 * (u_curr[idx - 2 * nx_ref - 2] + u_curr[idx - 2 * nx_ref + 2] +
                   u_curr[idx + 2 * nx_ref - 2] + u_curr[idx + 2 * nx_ref + 2]));

        const float lap = (w_ax * lap_ax + w_dg * lap_dg) * inv_dx2;

        // 4th-order Dablain / Lax-Wendroff temporal dispersion correction:
        // (c^4 * dt^4 / 12) * nabla^4(u)
        const float dxx = u_curr[idx - 1] + u_curr[idx + 1] - 2.0f * u0;
        const float dzz = u_curr[idx - nx_ref] + u_curr[idx + nx_ref] - 2.0f * u0;
        const float biharm_approx =
            ((u_curr[idx - 2] - 4.0f * u_curr[idx - 1] + 6.0f * u0 -
              4.0f * u_curr[idx + 1] + u_curr[idx + 2]) +
             (u_curr[idx - 2 * nx_ref] - 4.0f * u_curr[idx - nx_ref] + 6.0f * u0 -
              4.0f * u_curr[idx + nx_ref] + u_curr[idx + 2 * nx_ref]) +
             2.0f * (u_curr[idx - nx_ref - 1] + u_curr[idx - nx_ref + 1] +
                     u_curr[idx + nx_ref - 1] + u_curr[idx + nx_ref + 1] -
                     2.0f * (dxx + dzz) - 4.0f * u0)) * (inv_dx2 * inv_dx2);

        const float c2 = c2_dt2[idx];
        u_next[idx] = 2.0f * u0 - u_prev[idx] + c2 * lap +
                      (0.08333333f * c2 * c2) * biharm_approx;
      }
    }

    u_next[sz_ref * nx_ref + sx_ref] +=
        c2_dt2[sz_ref * nx_ref + sx_ref] * wavelet[it] * inv_dx2;

    for (int r = 0; r < kNumReceivers; ++r) {
      const int rx_ref = rx_phys[r] + kPadRef;
      (*ref_traces)[r * kNt + it] = u_next[rz_ref * nx_ref + rx_ref];
    }

    u_prev.swap(u_curr);
    u_curr.swap(u_next);
  }

  ref_interior_wavefield->assign(phys_nx * phys_nz, 0.0f);
  for (int pz = 0; pz < phys_nz; ++pz) {
    for (int px = 0; px < phys_nx; ++px) {
      (*ref_interior_wavefield)[pz * phys_nx + px] =
          u_curr[(pz + kPadRef) * nx_ref + (px + kPadRef)];
    }
  }
}

struct ModelMetrics {
  double trace_nrms;
  double interior_nrms;
  double late_reflection_ratio;
  double trace_energy_ratio;
  bool is_finite;
};

ModelMetrics evaluate_candidate_on_model(
    int model_id,
    float f0_hz,
    int sx_phys,
    int sz_phys,
    int n_repeats,
    double* min_wall_ms_out) {
  const int phys_nx = kNx - 2 * kNPad;
  const int phys_nz = kNz - 2 * kNPad;

  std::vector<int> rx_phys(kNumReceivers);
  std::vector<int> rx_cand(kNumReceivers);
  for (int r = 0; r < kNumReceivers; ++r) {
    rx_phys[r] = 4 + (r * (phys_nx - 8)) / (kNumReceivers - 1);
    rx_cand[r] = rx_phys[r] + kNPad;
  }

  std::vector<float> ref_traces;
  std::vector<float> ref_interior;
  run_gold_reference_solver(
      model_id, f0_hz, sx_phys, sz_phys, rx_phys, 2, &ref_traces, &ref_interior);

  std::vector<float> vp_cand;
  build_velocity_model(model_id, kNx, kNz, kNPad, &vp_cand);
  std::vector<float> wavelet;
  build_ricker_wavelet(f0_hz, kNt, kDt, &wavelet);

  std::vector<float> cand_traces(kNumReceivers * kNt, 0.0f);
  std::vector<float> cand_wavefield(kNx * kNz, 0.0f);

  double best_ms = 1e9;
  for (int rep = 0; rep < n_repeats; ++rep) {
    auto t0 = std::chrono::steady_clock::now();
    propagate_seismic_wavefield(
        vp_cand.data(),
        wavelet.data(),
        kNx,
        kNz,
        kNPad,
        kNt,
        kDx,
        kDt,
        sx_phys + kNPad,
        sz_phys + kNPad,
        rx_cand.data(),
        2 + kNPad,
        kNumReceivers,
        cand_traces.data(),
        cand_wavefield.data());
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    if (ms < best_ms) best_ms = ms;
  }
  *min_wall_ms_out = best_ms;

  double diff_sq = 0.0;
  double ref_sq = 0.0;
  double cand_sq = 0.0;
  double late_diff_sq = 0.0;
  bool finite_ok = true;

  for (int r = 0; r < kNumReceivers; ++r) {
    for (int it = 0; it < kNt; ++it) {
      const float c_val = cand_traces[r * kNt + it];
      const float r_val = ref_traces[r * kNt + it];
      if (!std::isfinite(c_val)) finite_ok = false;
      const double d = static_cast<double>(c_val) - static_cast<double>(r_val);
      diff_sq += d * d;
      ref_sq += static_cast<double>(r_val) * static_cast<double>(r_val);
      cand_sq += static_cast<double>(c_val) * static_cast<double>(c_val);
      if (it >= 260) {
        late_diff_sq += d * d;
      }
    }
  }

  double wf_diff_sq = 0.0;
  double wf_ref_sq = 0.0;
  for (int pz = 0; pz < phys_nz; ++pz) {
    for (int px = 0; px < phys_nx; ++px) {
      const float c_val = cand_wavefield[(pz + kNPad) * kNx + (px + kNPad)];
      const float r_val = ref_interior[pz * phys_nx + px];
      if (!std::isfinite(c_val)) finite_ok = false;
      const double d = static_cast<double>(c_val) - static_cast<double>(r_val);
      wf_diff_sq += d * d;
      wf_ref_sq += static_cast<double>(r_val) * static_cast<double>(r_val);
    }
  }

  ModelMetrics m;
  m.trace_nrms = std::sqrt(diff_sq / std::max(ref_sq, 1e-18));
  m.interior_nrms = std::sqrt(wf_diff_sq / std::max(wf_ref_sq, 1e-18));
  m.late_reflection_ratio = std::sqrt(late_diff_sq / std::max(ref_sq, 1e-18));
  m.trace_energy_ratio = cand_sq / std::max(ref_sq, 1e-18);
  m.is_finite = finite_ok;
  return m;
}

// Extended-time CFL stability audit (Nt_long = 1400 steps)
bool verify_extended_cfl_stability(double* energy_ratio_out) {
  constexpr int kNtLong = 1400;
  std::vector<float> vp_cand;
  build_velocity_model(0, kNx, kNz, kNPad, &vp_cand);
  std::vector<float> wavelet;
  build_ricker_wavelet(22.0f, kNtLong, kDt, &wavelet);

  std::vector<int> rx_cand(kNumReceivers, kNx / 2);
  std::vector<float> traces_mid(kNumReceivers * (kNtLong / 2), 0.0f);
  std::vector<float> wf_mid(kNx * kNz, 0.0f);
  std::vector<float> traces_end(kNumReceivers * kNtLong, 0.0f);
  std::vector<float> wf_end(kNx * kNz, 0.0f);

  propagate_seismic_wavefield(
      vp_cand.data(), wavelet.data(), kNx, kNz, kNPad, kNtLong / 2, kDx, kDt,
      kNx / 2, kNPad + 4, rx_cand.data(), kNPad + 4, kNumReceivers,
      traces_mid.data(), wf_mid.data());

  propagate_seismic_wavefield(
      vp_cand.data(), wavelet.data(), kNx, kNz, kNPad, kNtLong, kDx, kDt,
      kNx / 2, kNPad + 4, rx_cand.data(), kNPad + 4, kNumReceivers,
      traces_end.data(), wf_end.data());

  double e_mid = 0.0;
  double e_end = 0.0;
  for (int i = 0; i < kNx * kNz; ++i) {
    if (!std::isfinite(wf_mid[i]) || !std::isfinite(wf_end[i])) {
      *energy_ratio_out = 999.0;
      return false;
    }
    e_mid += static_cast<double>(wf_mid[i]) * static_cast<double>(wf_mid[i]);
    e_end += static_cast<double>(wf_end[i]) * static_cast<double>(wf_end[i]);
  }
  if (e_mid < 1e-16) {
    *energy_ratio_out = 999.0;
    return false;
  }
  *energy_ratio_out = e_end / e_mid;
  return (*energy_ratio_out <= 1.05);
}

void dump_wavefields_json(const char* out_path) {
  const int phys_nx = kNx - 2 * kNPad;
  const int phys_nz = kNz - 2 * kNPad;
  std::vector<int> rx_phys(kNumReceivers);
  std::vector<int> rx_cand(kNumReceivers);
  for (int r = 0; r < kNumReceivers; ++r) {
    rx_phys[r] = 4 + (r * (phys_nx - 8)) / (kNumReceivers - 1);
    rx_cand[r] = rx_phys[r] + kNPad;
  }
  std::vector<float> ref_traces;
  std::vector<float> ref_interior;
  run_gold_reference_solver(
      0, 22.0f, phys_nx / 2, 2, rx_phys, 2, &ref_traces, &ref_interior);

  std::vector<float> vp_cand;
  build_velocity_model(0, kNx, kNz, kNPad, &vp_cand);
  std::vector<float> wavelet;
  build_ricker_wavelet(22.0f, kNt, kDt, &wavelet);
  std::vector<float> cand_traces(kNumReceivers * kNt, 0.0f);
  std::vector<float> cand_wavefield(kNx * kNz, 0.0f);
  propagate_seismic_wavefield(
      vp_cand.data(),
      wavelet.data(),
      kNx,
      kNz,
      kNPad,
      kNt,
      kDx,
      kDt,
      phys_nx / 2 + kNPad,
      2 + kNPad,
      rx_cand.data(),
      2 + kNPad,
      kNumReceivers,
      cand_traces.data(),
      cand_wavefield.data());

  FILE* fp = std::fopen(out_path, "w");
  if (!fp) return;
  std::fprintf(fp, "{\n  \"nx\": %d, \"nz\": %d, \"n_pad\": %d, \"nt\": %d,\n",
               kNx, kNz, kNPad, kNt);
  const int r_far = 38;
  std::fprintf(fp, "  \"far_receiver_index\": %d,\n  \"cand_far_trace\": [", r_far);
  for (int it = 0; it < kNt; ++it) {
    std::fprintf(fp, "%s%.6f", (it == 0 ? "" : ", "), cand_traces[r_far * kNt + it]);
  }
  std::fprintf(fp, "],\n  \"ref_far_trace\": [");
  for (int it = 0; it < kNt; ++it) {
    std::fprintf(fp, "%s%.6f", (it == 0 ? "" : ", "), ref_traces[r_far * kNt + it]);
  }
  std::fprintf(fp, "]\n}\n");
  std::fclose(fp);
}

}  // namespace

int main(int argc, char** argv) {
  const char* dump_path = nullptr;
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::strcmp(argv[i], "--dump-wavefields") == 0) {
      dump_path = argv[i + 1];
    }
  }
  if (dump_path != nullptr) {
    dump_wavefields_json(dump_path);
  }

  double ms_marmousi = 0.0;
  double ms_fault = 0.0;

  const int phys_nx = kNx - 2 * kNPad;
  ModelMetrics m1 = evaluate_candidate_on_model(
      0, 22.0f, phys_nx / 2, 2, 5, &ms_marmousi);
  ModelMetrics m2 = evaluate_candidate_on_model(
      1, 25.0f, phys_nx / 3, 2, 5, &ms_fault);

  double energy_ratio = 0.0;
  bool cfl_stable = verify_extended_cfl_stability(&energy_ratio) &&
                    m1.is_finite && m2.is_finite;

  double total_ms = ms_marmousi + ms_fault;
  double total_gcells =
      2.0 * static_cast<double>(kNx) * static_cast<double>(kNz) *
      static_cast<double>(kNt) * 1e-9;
  double throughput_gcell_s = total_gcells / (total_ms * 1e-3);

  std::printf(
      "{\n"
      "  \"cfl_stable\": %s,\n"
      "  \"late_energy_ratio\": %.6f,\n"
      "  \"wall_time_ms\": %.4f,\n"
      "  \"throughput_gcell_s\": %.4f,\n"
      "  \"marmousi\": {\n"
      "    \"trace_nrms\": %.6f,\n"
      "    \"interior_nrms\": %.6f,\n"
      "    \"late_reflection_ratio\": %.6f,\n"
      "    \"trace_energy_ratio\": %.6f,\n"
      "    \"wall_time_ms\": %.4f\n"
      "  },\n"
      "  \"subsalt_fault\": {\n"
      "    \"trace_nrms\": %.6f,\n"
      "    \"interior_nrms\": %.6f,\n"
      "    \"late_reflection_ratio\": %.6f,\n"
      "    \"trace_energy_ratio\": %.6f,\n"
      "    \"wall_time_ms\": %.4f\n"
      "  }\n"
      "}\n",
      cfl_stable ? "true" : "false",
      energy_ratio,
      total_ms,
      throughput_gcell_s,
      m1.trace_nrms,
      m1.interior_nrms,
      m1.late_reflection_ratio,
      m1.trace_energy_ratio,
      ms_marmousi,
      m2.trace_nrms,
      m2.interior_nrms,
      m2.late_reflection_ratio,
      m2.trace_energy_ratio,
      ms_fault);
  return 0;
}

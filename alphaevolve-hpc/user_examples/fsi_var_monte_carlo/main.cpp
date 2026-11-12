// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifdef USE_MPI
#include <mpi.h>
#endif
#include <immintrin.h>
#include <x86intrin.h>
#include <omp.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <vector>

constexpr int NUM_FACTORS = 64;
constexpr int NUM_INSTRUMENTS = 512;
constexpr int NUM_REGIMES = 4;

struct alignas(32) PortfolioSoA {
    int type[NUM_INSTRUMENTS];       // 0: Put/Call, 1: Up-and-Out Call, 2: Worst-of-2 Put, 3: Variance Swap
    int f1[NUM_INSTRUMENTS];         // Primary risk factor index [0..63]
    int f2[NUM_INSTRUMENTS];         // Secondary risk factor index [0..63]
    double weight[NUM_INSTRUMENTS];  // Signed position notional ($M)
    double strike[NUM_INSTRUMENTS];  // Option strike K (around 100.0)
    double barrier[NUM_INSTRUMENTS]; // Knock-out barrier H
    double vol_dt[NUM_INSTRUMENTS];  // 10-day factor sensitivity sigma_i * sqrt(10/252)
    double base_val[NUM_INSTRUMENTS];// Today's mark-to-market position value V_0

    // Pre-computed analytical portfolio loss sensitivities:
    // factor_delta[f] = dL/dX_f, factor_gamma[f] = d^2L/dX_f^2 at X = 0
    double factor_delta[NUM_FACTORS];
    double factor_gamma[NUM_FACTORS];

    // Pre-computed Z-space sensitivities where X = L * Z, Z ~ N(0, I_64):
    // z_delta[d] = (L^T * factor_delta)_d = dL/dZ_d at Z = 0
    // z_gamma[d] = d^2L/dZ_d^2 at Z = 0
    // tail_dir[d] = z_delta[d] / ||z_delta||_2 (unit direction of steepest portfolio loss in Z-space)
    double z_delta[NUM_FACTORS];
    double z_gamma[NUM_FACTORS];
    double tail_dir[NUM_FACTORS];
};

inline double evaluate_instrument_payoff(
    int type, double s1, double s2, double x1, double x2,
    double strike, double barrier, double vol_dt) {
    if (type == 0) {
        // Protective put / short put exposure
        return std::max(0.0, strike - s1);
    } else if (type == 1) {
        // Up-and-out call with smooth digital barrier transition
        if (s1 >= barrier) {
            return 0.0;
        }
        return std::max(0.0, s1 - strike);
    } else if (type == 2) {
        // Worst-of-2 rainbow put option
        double worst_s = std::min(s1, s2);
        return std::max(0.0, strike - worst_s);
    } else {
        // Quadratic variance swap + skewness caplet
        double rv = 0.5 * (x1 * x1 + x2 * x2) * (vol_dt * 10.0);
        return 12.0 * (rv - strike * 0.01);
    }
}

inline double evaluate_portfolio_loss_scalar(const PortfolioSoA& p, const double* X) {
    double total_loss = 0.0;
    for (int i = 0; i < NUM_INSTRUMENTS; ++i) {
        double x1 = X[p.f1[i]];
        double x2 = X[p.f2[i]];
        double vdt = p.vol_dt[i];
        // Second-order exponential spot price map S = 100 * exp(vdt * x - 0.5 * vdt^2)
        double arg1 = vdt * x1 - 0.5 * vdt * vdt;
        double arg2 = vdt * x2 - 0.5 * vdt * vdt;
        double s1 = 100.0 * std::exp(arg1);
        double s2 = 100.0 * std::exp(arg2);
        double v_t = evaluate_instrument_payoff(
            p.type[i], s1, s2, x1, x2, p.strike[i], p.barrier[i], vdt);
        // Portfolio loss L = sum_i weight_i * (base_val_i - V_i(X))
        total_loss += p.weight[i] * (p.base_val[i] - v_t);
    }
    return total_loss;
}

// ////////////////////////////////////////////////////////////////////////////
// EVOLVE-BLOCK-START
void run_rank_tail_mc(
    const PortfolioSoA& port,
    const double* cholesky_L,
    int paths_per_seed,
    uint64_t seed_base,
    int rank,
    int num_ranks,
    double& out_var_99,
    double& out_cvar_999,
    double& out_mean_weight) {
    int local_paths = paths_per_seed / std::max(1, num_ranks);
    std::mt19937_64 rng(seed_base + static_cast<uint64_t>(rank) * 999983ULL);
    std::normal_distribution<double> std_norm(0.0, 1.0);

    std::vector<double> losses(local_paths, 0.0);
    std::vector<double> weights(local_paths, 1.0);

    double Z[NUM_FACTORS];
    double X[NUM_FACTORS];

    // Baseline Naive Crude Monte Carlo: un-tilted Z ~ N(0, I), scalar matvec & pricing
    for (int p = 0; p < local_paths; ++p) {
        for (int d = 0; d < NUM_FACTORS; ++d) {
            Z[d] = std_norm(rng);
        }
        for (int i = 0; i < NUM_FACTORS; ++i) {
            double sum = 0.0;
            for (int j = 0; j <= i; ++j) {
                sum += cholesky_L[i * NUM_FACTORS + j] * Z[j];
            }
            X[i] = sum;
        }
        losses[p] = evaluate_portfolio_loss_scalar(port, X);
        weights[p] = 1.0;
    }

    double sum_w = 0.0;
    for (int p = 0; p < local_paths; ++p) {
        sum_w += weights[p];
    }
    out_mean_weight = sum_w / static_cast<double>(local_paths);

    // Sort losses descending to compute empirical 99.0% VaR and 99.9% CVaR
    std::sort(losses.begin(), losses.end(), std::greater<double>());
    int idx_99 = std::max(0, static_cast<int>(std::floor(0.01 * local_paths)) - 1);
    int tail_count_999 = std::max(1, static_cast<int>(std::round(0.001 * local_paths)));

    out_var_99 = losses[idx_99];
    double tail_sum = 0.0;
    for (int k = 0; k < tail_count_999; ++k) {
        tail_sum += losses[k];
    }
    out_cvar_999 = tail_sum / static_cast<double>(tail_count_999);
}
// EVOLVE-BLOCK-END
// ////////////////////////////////////////////////////////////////////////////

void build_regime_portfolio_and_cholesky(
    int regime_id,
    PortfolioSoA& port,
    std::vector<double>& cholesky_L) {
    cholesky_L.assign(NUM_FACTORS * NUM_FACTORS, 0.0);

    // Construct positive-definite correlation matrix C for the regime
    double base_rho = 0.28;
    double intra_sector_rho = 0.55;
    double vol_mult = 1.0;
    double strike_shift = 0.0;

    if (regime_id == 1) {
        // Regime 1: 2008 Systemic Crash Correlation Shock (correlations surge toward 0.78)
        base_rho = 0.62;
        intra_sector_rho = 0.82;
        vol_mult = 1.35;
    } else if (regime_id == 2) {
        // Regime 2: 2020 Volatility Spike (1.75x vol scaling, moderate correlation)
        base_rho = 0.42;
        intra_sector_rho = 0.68;
        vol_mult = 1.75;
    } else if (regime_id == 3) {
        // Regime 3: Held-Out Stress Portfolio (shifted strikes + cross-sector skew)
        base_rho = 0.48;
        intra_sector_rho = 0.74;
        vol_mult = 1.45;
        strike_shift = 2.5;
    }

    std::vector<double> cov(NUM_FACTORS * NUM_FACTORS, 0.0);
    for (int i = 0; i < NUM_FACTORS; ++i) {
        for (int j = 0; j < NUM_FACTORS; ++j) {
            if (i == j) {
                cov[i * NUM_FACTORS + j] = 1.0;
            } else {
                bool same_sector = ((i / 8) == (j / 8));
                double decay = std::exp(-0.03 * std::abs(i - j));
                cov[i * NUM_FACTORS + j] = (same_sector ? intra_sector_rho : base_rho) * decay;
            }
        }
    }

    // Cholesky decomposition cov = L * L^T
    for (int i = 0; i < NUM_FACTORS; ++i) {
        for (int j = 0; j <= i; ++j) {
            double sum = cov[i * NUM_FACTORS + j];
            for (int k = 0; k < j; ++k) {
                sum -= cholesky_L[i * NUM_FACTORS + k] * cholesky_L[j * NUM_FACTORS + k];
            }
            if (i == j) {
                cholesky_L[i * NUM_FACTORS + i] = std::sqrt(std::max(1e-9, sum));
            } else {
                cholesky_L[i * NUM_FACTORS + j] = sum / cholesky_L[j * NUM_FACTORS + j];
            }
        }
    }

    // Populate 2,048 exotic derivative instruments deterministically
    std::mt19937_64 prng(20260419ULL + static_cast<uint64_t>(regime_id == 3 ? 777 : 0));
    std::uniform_real_distribution<double> u01(0.0, 1.0);

    double zero_X[NUM_FACTORS] = {0.0};
    for (int i = 0; i < NUM_INSTRUMENTS; ++i) {
        // Dominantly smooth put, rainbow, and variance positions so portfolio loss is strongly convex in tail
        int r_type = i % 8;
        if (r_type < 4) {
            port.type[i] = 0; // European Put
        } else if (r_type < 6) {
            port.type[i] = 2; // Worst-of-2 Rainbow Put
        } else if (r_type == 6) {
            port.type[i] = 3; // Variance Swap
        } else {
            port.type[i] = 1; // Up-and-Out Call
        }

        port.f1[i] = i % NUM_FACTORS;
        port.f2[i] = (i * 7 + 13) % NUM_FACTORS;
        if (port.f2[i] == port.f1[i]) {
            port.f2[i] = (port.f1[i] + 1) % NUM_FACTORS;
        }

        double base_vol = (0.032 + 0.024 * u01(prng)) * vol_mult;
        port.vol_dt[i] = base_vol;
        port.strike[i] = 98.0 + 10.0 * u01(prng) + strike_shift;
        port.barrier[i] = 122.0 + 12.0 * u01(prng);

        // Net short put / short variance dealer book -> large losses when X_f < 0 (market crash)
        if (port.type[i] == 1) {
            port.weight[i] = 0.06 + 0.04 * u01(prng);
        } else {
            port.weight[i] = -(0.12 + 0.10 * u01(prng));
        }

        double s0 = 100.0 * std::exp(-0.5 * base_vol * base_vol);
        port.base_val[i] = evaluate_instrument_payoff(
            port.type[i], s0, s0, 0.0, 0.0, port.strike[i], port.barrier[i], base_vol);
    }

    // Finite-difference sensitivities dL/dX_f and d^2L/dX_f^2 around X = 0
    double eps = 1e-3;
    double L0 = evaluate_portfolio_loss_scalar(port, zero_X);
    for (int f = 0; f < NUM_FACTORS; ++f) {
        double xp[NUM_FACTORS] = {0.0};
        double xm[NUM_FACTORS] = {0.0};
        xp[f] = eps;
        xm[f] = -eps;
        double Lp = evaluate_portfolio_loss_scalar(port, xp);
        double Lm = evaluate_portfolio_loss_scalar(port, xm);
        port.factor_delta[f] = (Lp - Lm) / (2.0 * eps);
        port.factor_gamma[f] = (Lp - 2.0 * L0 + Lm) / (eps * eps);
    }

    // Map sensitivities to independent standard-normal Z-space (X = L * Z)
    double norm_sq = 0.0;
    for (int d = 0; d < NUM_FACTORS; ++d) {
        double dz = 0.0;
        double g_diag = 0.0;
        for (int f = d; f < NUM_FACTORS; ++f) {
            double l_fd = cholesky_L[f * NUM_FACTORS + d];
            dz += l_fd * port.factor_delta[f];
            g_diag += l_fd * l_fd * port.factor_gamma[f];
        }
        port.z_delta[d] = dz;
        port.z_gamma[d] = g_diag;
        norm_sq += dz * dz;
    }
    double inv_norm = 1.0 / std::sqrt(std::max(1e-12, norm_sq));
    for (int d = 0; d < NUM_FACTORS; ++d) {
        port.tail_dir[d] = port.z_delta[d] * inv_norm;
    }
}

int main(int argc, char* argv[]) {
#ifdef USE_MPI
    MPI_Init(&argc, &argv);
    int mpi_rank = 0, mpi_size = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &mpi_rank);
    MPI_Comm_size(MPI_COMM_WORLD, &mpi_size);
#else
    int mpi_rank = 0, mpi_size = 1;
#endif

    int paths_per_seed = (argc > 1) ? std::stoi(argv[1]) : 8192;
    int num_seeds = (argc > 2) ? std::stoi(argv[2]) : 16;

    std::vector<PortfolioSoA> portfolios(NUM_REGIMES);
    std::vector<std::vector<double>> choleskys(NUM_REGIMES);
    for (int r = 0; r < NUM_REGIMES; ++r) {
        build_regime_portfolio_and_cholesky(r, portfolios[r], choleskys[r]);
    }

#ifdef USE_MPI
    MPI_Barrier(MPI_COMM_WORLD);
#endif
    auto t_start = std::chrono::high_resolution_clock::now();

    double regime_mean_var99[NUM_REGIMES] = {0.0};
    double regime_std_var99[NUM_REGIMES] = {0.0};
    double regime_mean_cvar999[NUM_REGIMES] = {0.0};
    double regime_std_cvar999[NUM_REGIMES] = {0.0};
    double regime_mean_w[NUM_REGIMES] = {0.0};

    for (int r = 0; r < NUM_REGIMES; ++r) {
        std::vector<double> local_var99(num_seeds, 0.0);
        std::vector<double> local_cvar999(num_seeds, 0.0);
        std::vector<double> local_w(num_seeds, 0.0);

#ifndef USE_MPI
        #pragma omp parallel for schedule(static)
#endif
        for (int s = mpi_rank; s < num_seeds; s += mpi_size) {
            uint64_t seed_base = 1000003ULL * static_cast<uint64_t>(r + 1)
                               + 10007ULL * static_cast<uint64_t>(s + 1);
            double v99 = 0.0, cv999 = 0.0, mw = 0.0;
            run_rank_tail_mc(
                portfolios[r],
                choleskys[r].data(),
                paths_per_seed,
                seed_base,
                0,
                1,
                v99,
                cv999,
                mw);
            local_var99[s] = v99;
            local_cvar999[s] = cv999;
            local_w[s] = mw;
        }

#ifdef USE_MPI
        MPI_Allreduce(MPI_IN_PLACE, local_var99.data(), num_seeds, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
        MPI_Allreduce(MPI_IN_PLACE, local_cvar999.data(), num_seeds, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
        MPI_Allreduce(MPI_IN_PLACE, local_w.data(), num_seeds, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
#endif

        double sum_v = 0.0, sum_cv = 0.0, sum_w = 0.0;
        for (int s = 0; s < num_seeds; ++s) {
            sum_v += local_var99[s];
            sum_cv += local_cvar999[s];
            sum_w += local_w[s];
        }
        double mean_v = sum_v / num_seeds;
        double mean_cv = sum_cv / num_seeds;
        double mean_w = sum_w / num_seeds;

        double sq_v = 0.0, sq_cv = 0.0;
        for (int s = 0; s < num_seeds; ++s) {
            double dv = local_var99[s] - mean_v;
            double dcv = local_cvar999[s] - mean_cv;
            sq_v += dv * dv;
            sq_cv += dcv * dcv;
        }
        double denom = static_cast<double>(std::max(1, num_seeds - 1));
        double inv_sqrt_seeds = 1.0 / std::sqrt(static_cast<double>(std::max(1, num_seeds)));
        regime_mean_var99[r] = mean_v;
        regime_std_var99[r] = std::sqrt(sq_v / denom) * inv_sqrt_seeds;
        regime_mean_cvar999[r] = mean_cv;
        regime_std_cvar999[r] = std::sqrt(sq_cv / denom) * inv_sqrt_seeds;
        regime_mean_w[r] = mean_w;
    }

#ifdef USE_MPI
    MPI_Barrier(MPI_COMM_WORLD);
#endif
    auto t_end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> elapsed_ms = t_end - t_start;

    if (mpi_rank == 0) {
        std::cout << std::fixed << std::setprecision(6);
        std::cout << "{\n"
                  << "  \"wall_time_ms\": " << elapsed_ms.count() << ",\n"
                  << "  \"regimes\": [\n";
        for (int r = 0; r < NUM_REGIMES; ++r) {
            double weight_sum = regime_mean_w[r] * static_cast<double>(paths_per_seed);
            std::cout << "    {\n"
                      << "      \"id\": " << r << ",\n"
                      << "      \"var_99\": " << regime_mean_var99[r] << ",\n"
                      << "      \"var_se\": " << regime_std_var99[r] << ",\n"
                      << "      \"cvar_999\": " << regime_mean_cvar999[r] << ",\n"
                      << "      \"cvar_se\": " << regime_std_cvar999[r] << ",\n"
                      << "      \"mean_weight\": " << regime_mean_w[r] << ",\n"
                      << "      \"weight_sum\": " << weight_sum << "\n"
                      << "    }" << (r + 1 < NUM_REGIMES ? "," : "") << "\n";
        }
        std::cout << "  ]\n"
                  << "}" << std::endl;
    }

#ifdef USE_MPI
    MPI_Finalize();
#endif
    return 0;
}

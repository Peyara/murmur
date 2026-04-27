# Schnakenberg Formalization of σ_coarse

**Type:** Theory reference
**Target document location:** `docs/theory/schnakenberg_formalization.md`
**Scope:** Defines σ_coarse as a finite-window estimator of the Schnakenberg entropy production rate for the Markov jump process model of cloud-agent activity. Derives the estimator, characterizes its statistical properties, and identifies the regimes in which it is reliable.
**Companion document:** `theory/physics_foundations.md` for the broader theoretical framework. This document focuses on the σ_coarse estimator specifically.

---

## 1. Setup

Let $\mathcal{Z} = \{Z_1, \ldots, Z_n\}$ be the zone state space ($n = 6$ in the current system). Let $Q \in \mathbb{R}^{n \times n}$ be the rate matrix governing the Markov jump process with off-diagonal entries $Q_{ij} \geq 0$ and diagonal entries $Q_{ii} = -\sum_{j \neq i} Q_{ij}$. Let $\pi \in \Delta^{n-1}$ be the unique steady-state distribution of $Q$, satisfying $\pi^\top Q = 0$.

The mean entropy production rate at steady state is, as derived in `physics_foundations.md`:

$$\sigma = \sum_{i \neq j} \pi_i Q_{ij} \ln \frac{Q_{ij}}{Q_{ji}}$$

This is the asymptotic quantity we want to estimate. Equivalently, by the symmetrization argument in `physics_foundations.md` §3.3:

$$\sigma = \frac{1}{2} \sum_{i \neq j} J^*_{ij} \ln \frac{\pi_i Q_{ij}}{\pi_j Q_{ji}}$$

where $J^*_{ij} = \pi_i Q_{ij} - \pi_j Q_{ji}$ is the steady-state directed current.

---

## 2. The Estimator

We observe a single trajectory $X : [0, T] \to \mathcal{Z}$ over a finite window of length $T$ (in the MVP, $T = 15$ minutes). From this trajectory we extract:

- $N_{ij}$: the number of $Z_i \to Z_j$ transitions observed in the window.
- $T_i$: the total time spent in zone $Z_i$ during the window. (When the trajectory is right-continuous and starts at time $0$ in some zone, $\sum_i T_i = T$ exactly.)

### 2.1 Rate matrix estimator

The maximum-likelihood estimator of the off-diagonal rate matrix entries, given the observed transition counts and occupation times, is

$$\hat{Q}_{ij} = \frac{N_{ij}}{T_i} \quad (i \neq j)$$

This is a standard result for continuous-time Markov chain inference. Intuitively: the rate of $i \to j$ transitions is the count of such transitions divided by the time at risk (time spent in $Z_i$).

### 2.2 Steady-state estimator

The empirical steady-state distribution can be estimated either by the occupation fraction

$$\hat{\pi}^{\text{occ}}_i = \frac{T_i}{T}$$

or by solving $\hat{\pi}^\top \hat{Q} = 0$ for $\hat{\pi}$ given $\hat{Q}$. The two estimators are asymptotically equivalent; the occupation fraction is simpler and is what we use in the MVP.

### 2.3 σ_coarse: plug-in estimator

The plug-in estimator for the entropy production rate is obtained by substituting $\hat{Q}$ and $\hat{\pi}$ into the asymptotic formula:

$$\hat{\sigma} = \sum_{i \neq j} \hat{\pi}_i \hat{Q}_{ij} \ln \frac{\hat{Q}_{ij}}{\hat{Q}_{ji}}$$

Substituting $\hat{Q}_{ij} = N_{ij}/T_i$ and $\hat{\pi}_i = T_i/T$:

$$\hat{\pi}_i \hat{Q}_{ij} = \frac{T_i}{T} \cdot \frac{N_{ij}}{T_i} = \frac{N_{ij}}{T}$$

So the estimator simplifies to

$$\boxed{\hat{\sigma} = \frac{1}{T} \sum_{i \neq j} N_{ij} \ln \frac{N_{ij} / T_i}{N_{ji} / T_j}}$$

Note that the prefactor structure makes this the **transition-count-weighted** sum of log rate ratios. Each $i \to j$ transition contributes $\ln(\hat{Q}_{ij}/\hat{Q}_{ji})$ to the entropy production, and the average over the window is taken by dividing by $T$.

### 2.4 Reduction when occupation times are similar

If the trajectory spends comparable time in each zone — i.e., $T_i \approx T_j$ for all pairs — the log term simplifies:

$$\ln \frac{N_{ij} / T_i}{N_{ji} / T_j} \approx \ln \frac{N_{ij}}{N_{ji}}$$

and the estimator becomes

$$\hat{\sigma} \approx \frac{1}{T} \sum_{i \neq j} N_{ij} \ln \frac{N_{ij}}{N_{ji}}$$

This is the "naive count-ratio" form. It is correct to leading order when occupation times are balanced and is convenient computationally. The MVP can use either form; the full form (with occupation times explicit) is more accurate when zone occupation is uneven.

### 2.5 Symmetrized form

Using the symmetry $\sum_{i \neq j} f(i,j) = \sum_{i \neq j} f(j,i)$, the estimator can be written symmetrically:

$$\hat{\sigma} = \frac{1}{2T} \sum_{i \neq j} (N_{ij} - N_{ji}) \ln \frac{N_{ij} / T_i}{N_{ji} / T_j}$$

This form makes the connection to currents explicit: $(N_{ij} - N_{ji})/T$ is the empirical net current $\hat{J}_{ij}$, and the estimator becomes

$$\hat{\sigma} = \frac{1}{2} \sum_{i \neq j} \hat{J}_{ij} \ln \frac{\hat{Q}_{ij}}{\hat{Q}_{ji}}$$

which is the empirical version of the current-times-affinity decomposition.

---

## 3. Statistical Properties

### 3.1 Consistency

As $T \to \infty$ with $Q$ fixed, $\hat{Q}_{ij} \to Q_{ij}$ almost surely, $\hat{\pi}_i \to \pi_i$ almost surely, and by continuous mapping $\hat{\sigma} \to \sigma$ almost surely. The estimator is consistent.

### 3.2 Bias at finite $T$

At finite $T$, $\hat{\sigma}$ has positive bias:

$$\mathbb{E}[\hat{\sigma}] \geq \sigma$$

This follows from Jensen's inequality applied to the logarithm. Heuristically: $\ln$ is concave, so $\mathbb{E}[\ln \hat{Q}_{ij}/\hat{Q}_{ji}] \leq \ln \mathbb{E}[\hat{Q}_{ij}/\hat{Q}_{ji}]$, but the contribution to $\hat{\sigma}$ is weighted by $\hat{Q}_{ij}$ itself, which is positively correlated with $\ln(\hat{Q}_{ij}/\hat{Q}_{ji})$. The combined effect is upward bias.

The bias is most severe when $N_{ij}$ or $N_{ji}$ is small. Specifically, when one count is zero, the log ratio is $\pm\infty$, and any regularization (§4.1) introduces a bias whose sign depends on the regularization choice.

The bias decays as $1/T$ for large $T$ when all entries of $Q$ are positive. For typical 15-minute windows in cloud activity, the bias is non-negligible and should be characterized empirically per environment.

### 3.3 Variance

A delta-method approximation to the variance is computable from the multinomial structure of the transition counts. The first-order variance is

$$\text{Var}(\hat{\sigma}) \approx \frac{1}{T^2} \sum_{i \neq j} \pi_i Q_{ij} \left( \ln \frac{Q_{ij}}{Q_{ji}} \right)^2$$

to leading order, with corrections from the joint distribution of transition counts. For implementation, the empirical version (substitute $\hat{Q}, \hat{\pi}$ for $Q, \pi$) gives a usable point estimate of the variance.

### 3.4 Lower bound from coarse-graining

If the underlying process operates on a finer state space than $\mathcal{Z}$ — for example, individual API methods rather than zones — the coarse-grained entropy production is a lower bound on the fine-grained entropy production:

$$\sigma_{\text{coarse-grained}} \leq \sigma_{\text{fine-grained}}$$

This is a general result (Esposito 2012). The implication: $\hat{\sigma}_{\text{coarse}}$ as computed at the zone level *underestimates* the true dissipation of the underlying activity. Anomalies visible only at sub-zone resolution will not register in $\sigma_{\text{coarse}}$.

---

## 4. Implementation

### 4.1 Regularization for small counts

When $N_{ij} = 0$ or $N_{ji} = 0$, the log ratio is undefined or infinite. Two approaches are standard.

**Pseudocount regularization:** Add a small $\varepsilon > 0$ to all counts:

$$\hat{\sigma}_\varepsilon = \frac{1}{T} \sum_{i \neq j} (N_{ij} + \varepsilon) \ln \frac{(N_{ij} + \varepsilon) / T_i}{(N_{ji} + \varepsilon) / T_j}$$

A typical choice is $\varepsilon = 0.5$. This biases the estimator toward zero (away from declaring large affinities at small samples). The bias is most pronounced when both $N_{ij}$ and $N_{ji}$ are small relative to $\varepsilon$.

**Pair filtering:** Restrict the sum to pairs where both $N_{ij} > 0$ and $N_{ji} > 0$:

$$\hat{\sigma}_{\text{filtered}} = \frac{1}{T} \sum_{\substack{i \neq j \\ N_{ij}, N_{ji} > 0}} N_{ij} \ln \frac{N_{ij} / T_i}{N_{ji} / T_j}$$

This excludes asymmetric-flux pairs (where one direction is observed and the other is not) from the sum. Because asymmetric flux is highly informative, filtering them out of $\hat{\sigma}$ loses signal. The MVP should record asymmetric-flux pairs as a separate observable rather than discarding them.

The recommendation: pair filtering for $\hat{\sigma}_{\text{coarse}}$, with asymmetric-flux pairs surfaced as a separate signal (e.g., `asymmetric_flux_count` or `divergent_edges`). Pseudocount regularization is acceptable but introduces estimator bias that is harder to interpret than the explicit exclusion of asymmetric pairs.

### 4.2 Diagonal handling

The diagonal of the transition-count matrix $N_{ii}$ corresponds to events that don't change zone (within-zone events). These do not contribute to inter-zone currents and should not appear in $\hat{\sigma}$. They are nonetheless informative for other observables (within-zone burstiness, zone dwell time distributions) and should be retained in the data.

### 4.3 Numerical considerations

The log ratio can have very large absolute values when the count ratio is large. To prevent overflow:

- Compute $\ln(N_{ij}+\varepsilon) - \ln(N_{ji}+\varepsilon)$ rather than $\ln((N_{ij}+\varepsilon)/(N_{ji}+\varepsilon))$.
- Clip the log ratio to a sane range (e.g., $[-20, 20]$) for numerical safety, with a flag when clipping occurs (clipping indicates extreme asymmetry that the estimator is not capturing well).

### 4.4 Reference implementation

Pseudocode for the recommended estimator:

```
def sigma_coarse(N, T_i, T, epsilon=0.0):
    """
    Estimator of Schnakenberg entropy production rate from window data.

    Args:
        N: n x n transition count matrix; N[i,j] = number of i->j transitions.
           Diagonal is ignored.
        T_i: length-n vector of zone occupation times.
        T: total window length.
        epsilon: pseudocount; if 0, use pair filtering instead.

    Returns:
        sigma: estimate of entropy production rate (nats per unit time).
        diagnostics: dict containing pair-level contributions, asymmetric-flux pairs,
                     numerical-clip events, and variance estimate.
    """
    n = len(T_i)
    sigma = 0.0
    diagnostics = {"contributions": {}, "asymmetric": [], "clipped": []}

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            N_ij, N_ji = N[i, j], N[j, i]

            if epsilon == 0:
                if N_ij == 0 or N_ji == 0:
                    if (N_ij > 0) != (N_ji > 0):
                        diagnostics["asymmetric"].append((i, j, N_ij, N_ji))
                    continue
                a, b = N_ij, N_ji
            else:
                a, b = N_ij + epsilon, N_ji + epsilon

            log_ratio = log(a / T_i[i]) - log(b / T_i[j])
            if abs(log_ratio) > 20:
                diagnostics["clipped"].append((i, j, log_ratio))
                log_ratio = sign(log_ratio) * 20

            contribution = (a / T) * log_ratio
            sigma += contribution
            diagnostics["contributions"][(i, j)] = contribution

    return sigma, diagnostics
```

The diagnostics enable post-hoc analysis of where σ_coarse is coming from and surface the asymmetric-flux structure for separate use.

---

## 5. Cycle Decomposition

The Schnakenberg formula §3 of `physics_foundations.md` decomposes $\sigma$ over fundamental cycles:

$$\sigma = \sum_\alpha J^{(\alpha)} A(\mathcal{C}_\alpha)$$

The plug-in estimator computes $\hat{\sigma}$ as a sum over edges, not cycles. The two are equivalent by the cycle-decomposition theorem, but the cycle form is more interpretable for diagnostics: which cycles contribute most to total entropy production?

### 5.1 Cycle currents from edge currents

Given empirical edge currents $\hat{J}_{ij} = (N_{ij} - N_{ji})/T$, the cycle currents $\hat{J}^{(\alpha)}$ are obtained by projecting $\hat{J}$ onto the fundamental cycle basis. Concretely:

1. Choose a spanning tree of the underlying undirected graph of $Q$. The spanning tree has $n-1$ edges; each non-tree edge defines a unique fundamental cycle.
2. For each non-tree edge $e = (i,j)$ with associated cycle $\mathcal{C}_e$, the cycle current is $\hat{J}^{(\alpha_e)} = \hat{J}_{ij}$.
3. Tree edges carry currents that are linear combinations of the non-tree cycle currents, determined by Kirchhoff's law (current conservation at each node).

For the 6-zone graph in the MVP, the number of fundamental cycles is $c = m - n + 1$ where $m$ is the number of edges with non-zero $Q$. With $n = 6$ and a fully connected graph ($m = 30$), $c = 25$. In practice not all 30 edges are populated, so $c$ is smaller.

### 5.2 Cycle affinities

Cycle affinities are computed directly from the rate matrix:

$$\hat{A}(\mathcal{C}_\alpha) = \sum_{(i,j) \in \mathcal{C}_\alpha} \ln \frac{\hat{Q}_{ij}}{\hat{Q}_{ji}}$$

where the sum is over edges of the cycle in the cycle's orientation, with appropriate signs.

### 5.3 Cycle-level diagnostics

The cycle-level decomposition gives $\hat{\sigma} = \sum_\alpha \hat{J}^{(\alpha)} \hat{A}(\mathcal{C}_\alpha)$, and ranking cycles by $|\hat{J}^{(\alpha)} \hat{A}(\mathcal{C}_\alpha)|$ identifies which cycles dominate the entropy production.

For Murmur, this is particularly informative: a window dominated by an IDENTITY → SECRET → DATA → EXFIL_RISK cycle is qualitatively different from one dominated by a COMPUTE → NETWORK → COMPUTE cycle, even if they have the same scalar $\hat{\sigma}$. Surfacing the dominant cycles is a natural extension of the dashboard's Flow Map.

---

## 6. Validation

The framework provides several testable predictions for the MVP data.

**Non-negativity.** $\hat{\sigma}_{\text{coarse}}$ should be non-negative. If the estimator goes negative, it indicates either small-sample bias near zero (where the variance can swamp the small mean) or numerical issues with the log. Negative values should be flagged but treated as zero.

**Vanishing for synthetic equilibrium data.** Generate synthetic windows where transition counts are symmetric ($N_{ij} = N_{ji}$ for all pairs). $\hat{\sigma}_{\text{coarse}}$ should be near zero, with deviations attributable to the bias characterized in §3.2.

**Scaling with attack intensity.** For the parameterized attack generator, $\hat{\sigma}_{\text{coarse}}$ should increase with the rate of anomalous activity injected, all else equal. The functional form of the increase is environment-dependent but should be monotone.

**Cycle structure under known attacks.** For attacks that traverse a specific cycle in the zone graph (e.g., explicit IDENTITY → SECRET → DATA → EXFIL_RISK), the cycle decomposition should localize the entropy production to that cycle and not to unrelated ones. This is a discriminative test of the framework.

**Insensitivity to window length above a threshold.** For sufficiently long windows, $\hat{\sigma}_{\text{coarse}}$ converges to its asymptotic value. Computing $\hat{\sigma}$ on a window and on its halves should give similar results once windows are long enough.

These validations are diagnostics for whether the framework is correctly applied to the data; failures indicate model assumptions being violated rather than implementation bugs in most cases.

---

## 7. Connection to Other Observables

### 7.1 Closure signals

The MVP's `closure_ratio` and `orphaned_privilege` signals measure flux imbalance at specific nodes — events that lack expected counterparts. In the Schnakenberg framework, these are local violations of node-level current conservation:

$$\text{closure imbalance at } Z_i = \sum_j (\hat{J}_{ji} - \hat{J}_{ij}) = -\frac{d \hat{p}_i}{dt}$$

For a window at steady state, this is zero. For a window where the distribution is changing (e.g., during a workflow that hasn't completed), it is non-zero. The closure signals are thus measurements of $\sigma_{na}$-related quantities (non-steady-state behavior) at specific nodes, complementary to the global $\hat{\sigma}_{\text{coarse}}$.

### 7.2 σ_relative

The proposed σ_relative signal — KL divergence between current residual zone flux and an EMA baseline — is, up to estimator details, an empirical proxy for the non-adiabatic component $\sigma_{na}$ defined in `physics_foundations.md` §4. The principled estimator of $\sigma_{na}$ requires estimating the instantaneous steady-state distribution $\pi(t)$ corresponding to the current rate matrix; the EMA baseline is one such estimate. A separate theory document on the σ_relative estimator is planned.

### 7.3 Provenance subtraction

Provenance subtraction (`compute_residual_risk`) corresponds to the rate-matrix decomposition $\hat{Q} = \sum_P \Delta \hat{Q}^{(P)} + \hat{Q}_{\text{residual}}$ described in `physics_foundations.md` §5. The residual entropy production $\hat{\sigma}_{\text{residual}}$ computed from $\hat{Q}_{\text{residual}}$ is the Schnakenberg-level analog of the score-level residual risk. The two are not equal in general (the score-level computation also includes invariants and other signals), but they should be correlated.

---

## 8. Summary

σ_coarse is the plug-in estimator of the Schnakenberg entropy production rate for the Markov jump process model of cloud-agent activity, computed from the zone-flux matrix and zone occupation times. The estimator is consistent, has positive bias at finite samples, and has variance that can be estimated to first order via the delta method.

The implementation requires care in handling small counts (pair filtering or pseudocount regularization), asymmetric flux (surfaced as a separate signal), and numerical edge cases (log clipping with diagnostics). The cycle decomposition of the estimator gives interpretable per-cycle contributions, which is the natural granularity for diagnosing where entropy production comes from.

The framework provides testable predictions (non-negativity, vanishing at equilibrium, scaling with attack intensity, cycle localization, window-length insensitivity) that validate or falsify the application of the model to MVP data.

---

## References

Schnakenberg, J. (1976). Network theory of microscopic and macroscopic behavior of master equation systems. *Reviews of Modern Physics*, 48(4), 571–585.

Esposito, M. (2012). Stochastic thermodynamics under coarse graining. *Physical Review E*, 85(4), 041125.

Polettini, M., & Esposito, M. (2014). Transient fluctuation theorems for the currents and initial equilibrium ensembles. *Journal of Statistical Mechanics*, P10033.

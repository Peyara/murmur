# Physics Foundations

**Type:** Theory reference
**Target document location:** `docs/theory/physics_foundations.md`
**Scope:** The non-equilibrium statistical mechanics framework underlying Murmur's signal layer. Defines the stochastic process model, derives the entropy production decomposition, and identifies the limits of the framework's applicability.
**Companion document:** `theory/schnakenberg_formalization.md` works through the σ_coarse estimator in detail. This document is the broader theoretical context.

---

## 1. The Process Model

Cloud-agent activity is modeled as a **continuous-time Markov jump process** on a finite state space.

### 1.1 State space

Let $\mathcal{Z} = \{Z_1, \ldots, Z_n\}$ be a finite set of zones. Each zone is a coarse-grained class of action types — for example, IDENTITY actions, SECRET-handling actions, DATA-plane actions, EXFIL_RISK actions. The coarse-graining is hand-designed in the current system; in extensions it may be learned.

A trajectory of one actor is a càdlàg function $X : [0, T] \to \mathcal{Z}$ that takes piecewise-constant values, with jumps at random times. Each event in the audit log corresponds to a jump $X(t^-) \to X(t)$ for some actor at some time $t$.

### 1.2 Rate matrix

The process is parameterized by a rate matrix $Q \in \mathbb{R}^{n \times n}$ with off-diagonal entries

$$Q_{ij} \geq 0 \quad (i \neq j)$$

giving the rate at which transitions $Z_i \to Z_j$ occur, and diagonal entries

$$Q_{ii} = -\sum_{j \neq i} Q_{ij}$$

The probability vector $p(t) \in \Delta^{n-1}$ giving the probability of being in each zone evolves under the master equation

$$\frac{d p_i}{dt} = \sum_{j} \big( p_j Q_{ji} - p_i Q_{ij} \big) = (p^\top Q)_i$$

where the sum is over $j \neq i$ in the off-diagonal terms (the diagonal cancels by construction).

### 1.3 Steady states

A steady state $\pi \in \Delta^{n-1}$ satisfies $\pi^\top Q = 0$. For an irreducible $Q$ (every zone reachable from every other via positive-rate transitions), the steady state exists and is unique.

The steady state is an **equilibrium** if it satisfies detailed balance:

$$\pi_i Q_{ij} = \pi_j Q_{ji} \quad \forall (i, j)$$

Otherwise it is a **non-equilibrium steady state** (NESS), characterized by persistent net currents around cycles in the transition graph.

For cloud activity, the steady state is generically a NESS. Sanctioned automation creates persistent asymmetric flux: schedulers fire periodically, services consume secrets and write data, the resulting cycle currents do not vanish. This is the central physical observation underlying the framework.

---

## 2. Currents and Cycles

### 2.1 Probability currents

Define the directed probability current from zone $i$ to zone $j$ as

$$J_{ij}(t) = p_i(t) Q_{ij} - p_j(t) Q_{ji}$$

At steady state with $p = \pi$, write $J^*_{ij} = \pi_i Q_{ij} - \pi_j Q_{ji}$.

Currents satisfy a **node-level conservation law**: at steady state, the sum of incoming currents equals the sum of outgoing currents at every node:

$$\sum_j J^*_{ji} = \sum_j J^*_{ij} = 0 \quad \forall i$$

Equivalently, $J^*$ is a divergence-free flow on the directed graph induced by $Q$.

### 2.2 Cycle decomposition of currents

The space of divergence-free flows on a directed graph is spanned by the fundamental cycles of the graph. Concretely: choose a spanning tree of the underlying undirected graph; each non-tree edge defines a unique fundamental cycle (the chord plus the tree path between its endpoints). The number of fundamental cycles is

$$c = m - n + 1$$

where $m$ is the number of (directed) edges with $Q_{ij} > 0$ and $n$ is the number of zones.

Any steady-state current $J^*$ can be written uniquely as

$$J^*_{ij} = \sum_{\alpha=1}^{c} J^{(\alpha)} \, \chi^{(\alpha)}_{ij}$$

where $\chi^{(\alpha)}_{ij} \in \{-1, 0, +1\}$ is the indicator of edge $(i,j)$ in cycle $\alpha$ (with sign according to orientation), and $J^{(\alpha)}$ is the scalar current flowing around cycle $\alpha$.

This decomposition is the basis for everything that follows. Detection of anomalous activity will be expressed as detection of anomalous cycle currents.

### 2.3 Cycle affinity

For a cycle $\mathcal{C} = (i_1 \to i_2 \to \cdots \to i_k \to i_1)$, define

$$A(\mathcal{C}) = \ln \frac{Q_{i_1 i_2} Q_{i_2 i_3} \cdots Q_{i_k i_1}}{Q_{i_2 i_1} Q_{i_3 i_2} \cdots Q_{i_1 i_k}}$$

This is the **cycle affinity** — the log-ratio of forward and reverse cycle products of rates. The affinity is a function of the rate matrix $Q$ alone, not of the steady-state distribution.

The cycle is **balanced** if $A(\mathcal{C}) = 0$, i.e., the product of forward rates around the cycle equals the product of reverse rates. Detailed balance is equivalent to $A(\mathcal{C}) = 0$ for all cycles, by the Kolmogorov criterion.

---

## 3. Entropy Production

### 3.1 Trajectory-level definition

For a càdlàg trajectory $X : [0, T] \to \mathcal{Z}$ with jumps at times $t_1 < t_2 < \cdots < t_N$, where the $\ell$-th jump is $X(t_\ell^-) = a_\ell \to b_\ell = X(t_\ell)$, the **stochastic entropy production** along the trajectory is

$$\Sigma[X] = \sum_{\ell=1}^{N} \ln \frac{Q_{a_\ell b_\ell}}{Q_{b_\ell a_\ell}}$$

This is a path functional: it depends on the specific sequence of jumps observed.

### 3.2 Mean entropy production rate

The expected entropy production per unit time at steady state is

$$\sigma = \lim_{T \to \infty} \frac{1}{T} \mathbb{E}_\pi[\Sigma[X]]$$

Computing this expectation:

$$\sigma = \sum_{i \neq j} \pi_i Q_{ij} \ln \frac{Q_{ij}}{Q_{ji}}$$

This expression sums the rate of $i \to j$ transitions (which is $\pi_i Q_{ij}$ at steady state) times the per-transition entropy contribution $\ln(Q_{ij}/Q_{ji})$.

### 3.3 Schnakenberg form

The above expression rearranges into a form due to Schnakenberg (1976) that decomposes $\sigma$ over the fundamental cycles of the rate graph.

Use the symmetry of the sum (each unordered pair $\{i,j\}$ appears twice, once in each direction):

$$\sigma = \frac{1}{2} \sum_{i \neq j} \big( \pi_i Q_{ij} - \pi_j Q_{ji} \big) \ln \frac{\pi_i Q_{ij}}{\pi_j Q_{ji}}$$

The factor $\pi_i Q_{ij} - \pi_j Q_{ji} = J^*_{ij}$ is the steady-state current. The logarithm separates as

$$\ln \frac{\pi_i Q_{ij}}{\pi_j Q_{ji}} = \ln \frac{Q_{ij}}{Q_{ji}} + \ln \frac{\pi_i}{\pi_j}$$

The $\ln(\pi_i / \pi_j)$ terms sum to zero around any cycle (it's a gradient and cycle-summed gradients vanish), and the cycle decomposition of $J^*$ from §2.2 substitutes in. The result:

$$\boxed{\sigma = \sum_{\alpha=1}^{c} J^{(\alpha)} \, A(\mathcal{C}_\alpha)}$$

This is the **Schnakenberg formula**: total entropy production rate equals the sum, over fundamental cycles, of cycle current times cycle affinity.

The interpretation is direct. A cycle contributes to dissipation only if both its current and its affinity are non-zero. A balanced cycle ($A = 0$) carries no entropy production regardless of its current. A current-free cycle ($J = 0$) carries no entropy production regardless of its affinity. Real dissipation requires both a thermodynamic driving force (affinity) and a flow (current) along it.

### 3.4 Properties

The mean entropy production rate has three properties that follow from the Schnakenberg form and from the underlying Markov structure.

**Non-negativity:** $\sigma \geq 0$, with equality iff detailed balance holds. This is the second-law content of the result. Proof: each term in the sum $\sum_{ij} (\pi_i Q_{ij} - \pi_j Q_{ji}) \ln(\pi_i Q_{ij} / \pi_j Q_{ji})$ has the form $(a - b) \ln(a/b) \geq 0$, with equality iff $a = b$. Hence $\sigma = 0$ iff $\pi_i Q_{ij} = \pi_j Q_{ji}$ for all pairs, which is detailed balance.

**Vanishing at equilibrium:** Equilibrium ($\pi_i Q_{ij} = \pi_j Q_{ji}$ for all pairs) implies $\sigma = 0$. The converse also holds for irreducible $Q$.

**Units:** $\sigma$ has units of nats per unit time (using natural log) or bits per unit time (with $\log_2$). The MVP reports σ_coarse in nats per window or normalized per second.

---

## 4. Adiabatic and Non-Adiabatic Decomposition

The Schnakenberg formula gives total entropy production at steady state. When the system is *not* at steady state — either because the rate matrix is changing (a "protocol") or because the distribution has not yet relaxed — total entropy production decomposes into two physically distinct components.

### 4.1 The decomposition

Following the standard formulation (Esposito and Van den Broeck 2010), define the entropy production rate as

$$\sigma(t) = \sigma_a(t) + \sigma_{na}(t)$$

where:

**Adiabatic (housekeeping) component:**

$$\sigma_a(t) = \sum_{i \neq j} p_i(t) Q_{ij} \ln \frac{p_i(t) Q_{ij}}{p_j(t) Q_{ji}} \cdot \delta_a$$

with the appropriate projection $\delta_a$ onto the steady-state-maintaining flow. Concretely: $\sigma_a$ is the entropy production that the system *would* exhibit if it were instantaneously at the steady state $\pi(t)$ corresponding to the current rate matrix $Q(t)$. It captures the dissipation required to maintain the NESS — the cost of the persistent currents that are intrinsic to the steady state.

**Non-adiabatic (excess) component:**

$$\sigma_{na}(t) = \sum_{i} \frac{d p_i}{dt} \ln \frac{p_i(t)}{\pi_i(t)}$$

This is the dissipation due to the actual distribution $p(t)$ being different from the instantaneous steady state $\pi(t)$. It captures the cost of relaxation toward steady state, or of being driven away from it.

### 4.2 Properties

Both components are individually non-negative:

$$\sigma_a(t) \geq 0, \quad \sigma_{na}(t) \geq 0$$

This is a stronger statement than the second law. It means dissipation can be cleanly separated into "what's needed to keep this NESS running" and "what's extra because we're not yet at the NESS."

The non-adiabatic component vanishes when $p(t) = \pi(t)$ — i.e., whenever the distribution matches the instantaneous steady state. The adiabatic component vanishes only at equilibrium ($Q$ satisfying detailed balance).

### 4.3 Interpretation for the cloud-activity setting

The decomposition is the formal basis for distinguishing legitimate from anomalous activity in entropy-production terms.

**Adiabatic component for legitimate activity.** Sanctioned automation establishes a NESS with characteristic cycle currents (scheduler → service → resource → log). The rate matrix $Q$ is approximately stable across time, the distribution is near $\pi$, and entropy production is dominated by $\sigma_a$ — the housekeeping cost of running the legitimate workflows. This is non-zero, expected, and not a signal.

**Non-adiabatic component as anomaly signal.** Anomalous activity drives the system away from $\pi$. New actors, new resources touched, unusual flow patterns — all push $p(t) \neq \pi(t)$, generating non-adiabatic entropy production. $\sigma_{na}$ measures this excess directly.

**Implication for σ_relative.** The σ_relative signal proposed in the post-MVP roadmap (KL divergence between current residual zone flux and an EMA baseline) is, up to estimator details, an empirical proxy for $\sigma_{na}$. The non-adiabatic decomposition is its principled definition.

### 4.4 Protocol changes

When the rate matrix itself changes — for example, when a new sanctioned pattern is registered, adding rate to specific edges of the transition graph — the steady state $\pi(t)$ shifts. The system relaxes toward the new steady state on a timescale set by the spectral gap of $Q$.

During this relaxation, $\sigma_{na}(t)$ is elevated even though no anomaly is present: the distribution simply hasn't caught up to the new $\pi$ yet. This is the diabatic-lag phenomenon underlying the "false-positive transient" problem at pattern-registration events.

A counterdiabatic correction adds a transient extra term to $Q(t)$ during the protocol change, designed so that $p(t)$ tracks $\pi(t)$ exactly at all times and $\sigma_{na}(t) = 0$ throughout. The construction of such corrections for jump processes is given by the gauge-potential formalism developed in the quantum control literature (Demirplak and Rice, Berry) and extended to dissipative classical systems by Iram et al. (Nature Physics 2021).

---

## 5. Provenance Subtraction in the Schnakenberg Framework

Sanctioned patterns in Murmur correspond to subgraphs of the transition graph with specified rates. A pattern that says *"scheduler-fired job X triggers service Y, which writes to resource Z"* specifies a sequence of zone transitions with characteristic rates determined by the pattern's firing frequency.

In rate-matrix terms, registering a sanctioned pattern $P$ adds a contribution $\Delta Q^{(P)}$ to the rate matrix:

$$Q_{\text{observed}} = Q_{\text{residual}} + \sum_{P \in \text{sanctioned}} \Delta Q^{(P)}$$

where $\Delta Q^{(P)}_{ij}$ is non-zero only on the edges that pattern $P$ traverses, with magnitudes set by the pattern's firing rate.

By linearity of the cycle decomposition, the entropy production decomposes as

$$\sigma_{\text{observed}} = \sigma_{\text{sanctioned}} + \sigma_{\text{residual}} + \sigma_{\text{cross}}$$

where $\sigma_{\text{sanctioned}}$ is the entropy production attributable to sanctioned patterns alone, $\sigma_{\text{residual}}$ is the entropy production of the residual rate matrix, and $\sigma_{\text{cross}}$ is a cross-term that vanishes when sanctioned patterns and residual activity traverse disjoint cycles.

The MVP's `compute_residual_risk` function performs this subtraction at the score level. The Schnakenberg framework lifts the same operation to the entropy-production level:

$$\sigma_{\text{residual}} = \sigma_{\text{observed}} - \sigma_{\text{sanctioned}} - \sigma_{\text{cross}}$$

When sanctioned-pattern cycle structure is well-separated from anomalous-activity cycle structure (which is the assumption underlying provenance subtraction working at all), $\sigma_{\text{cross}}$ is small and the residual entropy production is dominated by $\sigma_{\text{residual}}$, which represents unattributed activity.

This re-expression of provenance subtraction in entropy-production terms is the connection point between the provenance layer and the physics-informed signal layer. Both are operating on the same underlying object.

---

## 6. Limits of the Framework

The Markov-jump-process formulation makes assumptions that are approximations in the cloud-activity setting. Each is a place where the framework may need extension.

### 6.1 Markovianity

The framework assumes the next jump depends only on the current zone, not on history. Real cloud activity has long-range dependencies. A scheduler firing at minute 2 may legitimately cause activity at minute 12 via a chain of services with internal state. A sanctioned pattern with multiple stages is non-Markovian by construction in the bare zone-state space.

This is mitigated by including memory in the state. Specifically: the state space can be augmented to $\mathcal{Z} \times \mathcal{H}$ where $\mathcal{H}$ is a coarse-graining of relevant history (e.g., "in the middle of pattern P, stage 3"). The augmented process is more nearly Markovian. The MVP's hand-engineered state is the bare zone, which is the simplest choice; the post-MVP learned representations effectively learn an augmented state that captures relevant history.

The diagnostic for whether bare-zone Markovianity is adequate: empirical rate matrices computed on disjoint sub-windows of a single window should be consistent. If they vary strongly — indicating that "what happens next" depends on what happened earlier in the window beyond what the bare zone state captures — the assumption is being violated.

### 6.2 Time-homogeneity within window

Rates are assumed constant within a 15-minute window. They aren't, strictly: scheduled jobs fire at specific times, and rates spike around those times. The approximation is acceptable for window-level $\sigma_{\text{coarse}}$ (which estimates window-averaged rates), but it predicts internal structure that the per-window estimate averages over.

A more refined treatment uses time-dependent rate matrices $Q(t)$ within the window. Estimating $Q(t)$ requires sub-window sampling, which is feasible only when event counts are large.

### 6.3 Coarse-graining

The 6-zone projection collapses within-zone structure. The framework still applies — the coarse-grained process is Markovian in the coarse-grained state space if the underlying process is Markovian, with caveats about the projection introducing memory (Esposito 2012).

The cost of coarse-graining is a lower bound on entropy production: $\sigma_{\text{coarse-grained}} \leq \sigma_{\text{fine-grained}}$. This means $\sigma_{\text{coarse}}$ as computed in the MVP is a *lower bound* on the true entropy production of the underlying activity. Anomalies that are visible only at finer-than-zone resolution will not be detected by $\sigma_{\text{coarse}}$ — they require either a finer coarse-graining or a learned representation that doesn't pre-commit to a fixed projection.

### 6.4 Steady-state assumption

The Schnakenberg cycle decomposition is a steady-state result. Within a 15-min window, we assume the process is approximately at steady state. This is a strong assumption; transient dynamics (the first few minutes after a scheduler fires) are not at steady state. The estimator described in `theory/schnakenberg_formalization.md` does not strictly require steady state — it is a finite-time estimator that converges to the steady-state $\sigma$ as window length grows — but its small-window bias is harder to characterize during transients.

The non-adiabatic decomposition (§4) explicitly handles non-steady-state behavior and is in this sense more general than the bare Schnakenberg form. When the system is at steady state, $\sigma_{na} = 0$ and the total reduces to the adiabatic part, which is what the cycle decomposition computes.

### 6.5 Single-actor vs. multi-actor

The framework as stated treats all activity as a single Markov process. Real cloud activity is many actors running concurrently and (mostly) independently. The right formal object is a product of independent Markov processes, with zone occupation summed over actors.

This works as long as actors are independent. The interesting case — and the one the framework needs to capture for provenance subtraction to make sense — is when one actor's activity *causes* another's. A scheduler firing causes a service to act; a service acting causes a write to a resource. These causal couplings are exactly what sanctioned patterns describe.

The right treatment is a Markov process on the joint state space of all actors, with rate matrix entries that include "actor $i$ in state $s$ causes actor $j$ to transition" terms. This is more elaborate than the bare per-actor framework. The MVP's implicit treatment — pool all actors into a single zone-flux matrix — is a coarse-graining of this joint process. The cost is similar to §6.3: it collapses information about who-caused-what, retaining only aggregate flow.

---

## 7. Summary

Cloud-agent activity is modeled as a continuous-time Markov jump process on a zone state space, parameterized by a rate matrix $Q$. The process generically settles at a non-equilibrium steady state characterized by persistent cycle currents, which Schnakenberg (1976) decomposes via a sum over fundamental cycles weighted by cycle affinities and currents.

The entropy production rate $\sigma$ separates into adiabatic (housekeeping for the NESS) and non-adiabatic (excess due to driving away from the NESS) components. Sanctioned cloud activity is dominated by $\sigma_a$; anomalous activity adds $\sigma_{na}$. Provenance subtraction has a clean interpretation as decomposition of the rate matrix into sanctioned and residual components, with the entropy production decomposing accordingly.

The framework's assumptions — Markovianity, time-homogeneity, fixed coarse-graining, steady state, independent actors — are all approximations. Each is a place where extensions of the framework (learned state representations, time-dependent rate matrices, finer-grained coarse-grainings, joint-process treatments) become motivated.

The companion document `theory/schnakenberg_formalization.md` works through the σ_coarse estimator in detail. Subsequent theory documents will cover the non-adiabatic decomposition estimator, the connection to learned representations via temporal point processes, and the counterdiabatic adaptation construction.

---

## References

Schnakenberg, J. (1976). Network theory of microscopic and macroscopic behavior of master equation systems. *Reviews of Modern Physics*, 48(4), 571–585.

Esposito, M., & Van den Broeck, C. (2010). Three faces of the second law. I. Master equation formulation. *Physical Review E*, 82(1), 011143.

Esposito, M. (2012). Stochastic thermodynamics under coarse graining. *Physical Review E*, 85(4), 041125.

Demirplak, M., & Rice, S. A. (2003). Adiabatic population transfer with control fields. *Journal of Physical Chemistry A*, 107(46), 9937–9945.

Berry, M. V. (2009). Transitionless quantum driving. *Journal of Physics A*, 42(36), 365303.

Iram, S., Dolson, E., Chiel, J., Pelesko, J., Krishnan, N., Güngör, Ö., Kuznets-Speck, B., Deffner, S., Ilker, E., Scott, J. G., & Hinczewski, M. (2021). Controlling the speed and trajectory of evolution with counterdiabatic driving. *Nature Physics*, 17, 135–142.

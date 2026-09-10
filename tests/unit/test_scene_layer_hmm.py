"""The scene-layer induction tool (scripts/scene_layer_hmm.py).

The tool produced a negative result that now sits in the study
(MASTERS_BLOCK_GRAMMAR_STUDY.md section 12), so its machinery is worth a
guard: a forward-backward or Baum-Welch bug would have manufactured that
conclusion. Tested against synthetic sequences with a known answer, so no
corpus and no LLM are needed.
"""
import importlib.util
import os

import numpy as np
import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                     "scripts", "scene_layer_hmm.py")
_spec = importlib.util.spec_from_file_location("scene_layer_hmm", _PATH)
slh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(slh)

M = len(slh.MODES)


# ---- forward-backward --------------------------------------------------------

def test_loglik_matches_brute_force_enumeration():
    # With 2 states and a short sequence the exact likelihood is a sum over
    # every state path; the scaled recursion must agree.
    rng = np.random.default_rng(0)
    pi = np.array([0.3, 0.7])
    A = np.array([[0.8, 0.2], [0.4, 0.6]])
    B = rng.dirichlet(np.ones(M), size=2)
    obs = np.array([3, 4, 3, 5], dtype=np.intp)

    total = 0.0
    for z0 in range(2):
        for z1 in range(2):
            for z2 in range(2):
                for z3 in range(2):
                    path = (z0, z1, z2, z3)
                    p = pi[z0] * B[z0, obs[0]]
                    for t in range(1, 4):
                        p *= A[path[t - 1], path[t]] * B[path[t], obs[t]]
                    total += p
    _, _, ll = slh._forward_backward(obs, pi, A, B)
    assert ll == pytest.approx(np.log(total), rel=1e-9)


def test_gamma_is_a_distribution_per_step():
    rng = np.random.default_rng(1)
    pi = rng.dirichlet(np.ones(3))
    A = rng.dirichlet(np.ones(3), size=3)
    B = rng.dirichlet(np.ones(M), size=3)
    obs = rng.integers(0, M, size=40).astype(np.intp)
    gamma, xi, _ = slh._forward_backward(obs, pi, A, B)
    assert np.allclose(gamma.sum(1), 1.0)
    # xi totals the expected number of transitions, one per step boundary.
    assert xi.sum() == pytest.approx(len(obs) - 1, rel=1e-6)


# ---- Baum-Welch --------------------------------------------------------------

def _synthetic(n_seq=20, T=40, seed=0):
    """Two well-separated states: one emits mostly DIALOGUE, one mostly ACTION,
    each sticky. A correct fitter should recover that structure."""
    rng = np.random.default_rng(seed)
    d, a = slh.IDX["DIALOGUE"], slh.IDX["ACTION"]
    B = np.full((2, M), 0.01)
    B[0, d] = 0.94
    B[1, a] = 0.94
    B /= B.sum(1, keepdims=True)
    A = np.array([[0.95, 0.05], [0.05, 0.95]])
    seqs = []
    for _ in range(n_seq):
        z = rng.integers(2)
        s = np.empty(T, dtype=np.intp)
        for t in range(T):
            s[t] = rng.choice(M, p=B[z])
            z = rng.choice(2, p=A[z])
        seqs.append(s)
    return seqs


def test_baum_welch_likelihood_never_decreases():
    seqs = _synthetic()
    pi, A, B, ll, _ = slh.fit(seqs, K=2, seed=0, iters=3)
    lls = []
    for iters in (1, 2, 3, 4, 5):
        lls.append(slh.fit(seqs, K=2, seed=0, iters=iters)[3])
    assert all(b >= a - 1e-9 for a, b in zip(lls, lls[1:])), lls


def test_baum_welch_recovers_planted_states():
    seqs = _synthetic()
    pi, A, B, ll, _ = slh.best_fit(seqs, K=2, iters=120)
    dominant = {slh.MODES[i] for i in B.argmax(1)}
    assert dominant == {"DIALOGUE", "ACTION"}
    assert np.all(np.diag(A) > 0.8)          # both states are sticky


def test_the_best_likelihood_restart_is_the_correct_one():
    """Why best_fit selects on likelihood, and why the restart count matters.

    Individual restarts collapse to a degenerate fit about half the time
    (both states dominated by one mode, no stickiness), so a single run is
    not trustworthy. What makes best-of-N sound is that the degenerate fits
    are also the lower-likelihood ones, so argmax over restarts picks the
    right model. A regression here would silently weaken every conclusion
    drawn from a fitted model.
    """
    seqs = _synthetic(seed=1)
    scored = []
    for seed in range(6):
        pi, A, B, ll, _ = slh.fit(seqs, K=2, seed=seed, iters=120)
        good = ({slh.MODES[i] for i in B.argmax(1)} == {"DIALOGUE", "ACTION"}
                and bool(np.all(np.diag(A) > 0.8)))
        scored.append((ll, good))
    assert any(g for _, g in scored), "no restart recovered the structure"
    assert not all(g for _, g in scored), "expected some degenerate restarts"
    assert max(scored)[1], "the highest-likelihood restart was degenerate"


def test_viterbi_tracks_the_planted_segmentation():
    # Needs the full synthetic sample and best_fit's full restart count: on a
    # small sample, or from a single start, Baum-Welch lands in a degenerate
    # optimum and the test would be measuring that, not Viterbi.
    seqs = _synthetic(seed=2)
    pi, A, B, _, _ = slh.best_fit(seqs, K=2, iters=120)
    d = slh.IDX["DIALOGUE"]
    dialogue_state = int(B[:, d].argmax())
    path = slh.viterbi(seqs[0], pi, A, B)
    agree = np.mean((path == dialogue_state) == (seqs[0] == d))
    assert agree > 0.85


# ---- the statistic under test ------------------------------------------------

def test_return_rate_counts_genuine_switches_only():
    # A B A -> one switch, one return. A A A -> no genuine switch at all.
    assert slh.return_rate([np.array([0, 1, 0])]) == (1.0, 1)
    assert slh.return_rate([np.array([0, 0, 0])])[1] == 0
    assert slh.return_rate([np.array([0, 1, 2])]) == (0.0, 1)


def test_sampling_reproduces_a_planted_sticky_chain():
    # A near-deterministic 2-state chain emitting one mode each: switches are
    # rare and never return immediately, so the rate must be ~0.
    pi = np.array([1.0, 0.0])
    A = np.array([[0.9, 0.1], [0.0, 1.0]])
    B = np.zeros((2, M))
    B[0, slh.IDX["DIALOGUE"]] = 1.0
    B[1, slh.IDX["ACTION"]] = 1.0
    rng = np.random.default_rng(0)
    seqs = slh.sample(pi, A, B, [50] * 20, rng)
    assert slh.return_rate(seqs)[0] == 0.0


def test_name_states_disambiguates_shared_dominant_modes():
    B = np.zeros((3, M))
    B[0, slh.IDX["DIALOGUE"]] = 1.0
    B[1, slh.IDX["DIALOGUE"]] = 1.0
    B[2, slh.IDX["ACTION"]] = 1.0
    names = slh.name_states(B)
    assert names[2] == "ACTION"
    assert names[0] != names[1] and set(names[:2]) == {"DIALOGUE_1",
                                                       "DIALOGUE_2"}

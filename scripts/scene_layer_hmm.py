#!/usr/bin/env python3
"""Induce the L2 scene layer from the masters corpus (study section 11, gap 1).

Nothing in the corpus labels scenes. Section 7 of
docs/MASTERS_BLOCK_GRAMMAR_STUDY.md argues one must exist: the masters return
to an interrupted block mode about 50% more often than a flat Markov chain
predicts (0.355 vs 0.238), and a persistent state above the block is the
natural explanation. This script induces that state directly, by fitting a
discrete HMM over the per-paragraph label sequences with Baum-Welch.

Sequences are units (chapters), so a hidden state never crosses a unit
boundary, matching the corpus discipline that block runs never do. Held-out
scoring splits by BOOK, so a state cannot be an artifact of one author's
habits. No LLM calls; numpy only.

Usage:
    python scripts/scene_layer_hmm.py                  # selection table
    python scripts/scene_layer_hmm.py --k 5 --report   # inspect one model
    python scripts/scene_layer_hmm.py --k 5 --json PATH  # emit scene_layer
"""

import argparse
import glob
import json
import os

import numpy as np

SIDE_DIR = os.path.join(os.path.dirname(__file__), "..",
                        "work", "corpus", "scores", "nd1_ab", "deepseek")
GIANTS = {"collins-womaninwhite", "eliot-middlemarch", "dickens-bleakhouse",
          "dumas-montecristo", "tolstoy-warandpeace"}
MODES = ["SETTING", "CHARACTER_DESC", "LORE", "DIALOGUE", "ACTION",
         "INTERIORITY", "TRANSITION"]
IDX = {m: i for i, m in enumerate(MODES)}


# ---- data --------------------------------------------------------------------

def load_sequences(include_giants=False):
    """{book: [unit label sequences]} as integer arrays."""
    books = {}
    for path in sorted(glob.glob(os.path.join(SIDE_DIR, "*.nd.json"))):
        name = os.path.basename(path)[:-len(".nd.json")]
        if not include_giants and name in GIANTS:
            continue
        with open(path) as f:
            d = json.load(f)
        seqs = []
        for u in sorted(d["metrics"]["block_rhythm"]["per_unit"],
                        key=lambda u: u["index"]):
            s = [IDX[l[0]] for l in u["labels"] if l and l[0] in IDX]
            if len(s) >= 2:
                seqs.append(np.asarray(s, dtype=np.intp))
        books[name] = seqs
    return books


# ---- HMM ---------------------------------------------------------------------

def _forward_backward(obs, pi, A, B, want_xi=True):
    """Scaled forward-backward. Returns (gamma, xi, loglik)."""
    Bo = B[:, obs].T
    T, K = Bo.shape
    alpha = np.empty((T, K))
    c = np.empty(T)
    a = pi * Bo[0]
    c[0] = a.sum() or 1e-300
    alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ A) * Bo[t]
        c[t] = a.sum() or 1e-300
        alpha[t] = a / c[t]
    beta = np.empty((T, K))
    beta[-1] = 1.0
    for t in range(T - 2, -1, -1):
        beta[t] = (A @ (Bo[t + 1] * beta[t + 1])) / c[t + 1]
    gamma = alpha * beta
    gamma /= np.maximum(gamma.sum(1, keepdims=True), 1e-300)
    xi = None
    if want_xi:
        w = (Bo[1:] * beta[1:]) / c[1:, None]
        xi = A * (alpha[:-1].T @ w)
    return gamma, xi, float(np.log(c).sum())


def fit(seqs, K, seed=0, iters=600, tol=1e-8):
    """Baum-Welch from a Dirichlet random start. Returns (pi, A, B, ll, iters)."""
    rng = np.random.default_rng(seed)
    M = len(MODES)
    pi = rng.dirichlet(np.ones(K))
    A = rng.dirichlet(np.ones(K) * 2.0, size=K)
    B = rng.dirichlet(np.ones(M) * 2.0, size=K)
    prev, it = -np.inf, 0
    for it in range(iters):
        pi_n = np.zeros(K)
        A_n = np.zeros((K, K))
        Bt_n = np.zeros((M, K))
        ll = 0.0
        for obs in seqs:
            g, x, l = _forward_backward(obs, pi, A, B)
            ll += l
            pi_n += g[0]
            A_n += x
            np.add.at(Bt_n, obs, g)
        pi = pi_n / pi_n.sum()
        A = A_n / np.maximum(A_n.sum(1, keepdims=True), 1e-300)
        B = Bt_n.T / np.maximum(Bt_n.T.sum(1, keepdims=True), 1e-300)
        if prev > -np.inf and abs(ll - prev) < tol * abs(prev):
            prev = ll
            break
        prev = ll
    return pi, A, B, prev, it


def best_fit(seqs, K, seeds=10, **kw):
    """Best of several random restarts.

    Baum-Welch finds local optima, and on this data many starts collapse to a
    degenerate fit: two states dominated by the same mode, a non-sticky
    transition matrix, no convergence inside the iteration cap. Measured on
    synthetic sequences with a planted 2-state structure, the
    highest-likelihood restart was the correct one every time, but individual
    restarts were correct only about half the time, so the restart count is
    what buys reliability. Ten is past where recovery saturated; do not lower
    it without re-measuring.
    """
    best = None
    for s in range(seeds):
        r = fit(seqs, K, seed=s, **kw)
        if best is None or r[3] > best[3]:
            best = r
    return best


def loglik(seqs, pi, A, B):
    return sum(_forward_backward(o, pi, A, B, want_xi=False)[2] for o in seqs)


def viterbi(obs, pi, A, B):
    T, K = len(obs), len(pi)
    lA, lB = np.log(A + 1e-300), np.log(B + 1e-300)
    d = np.log(pi + 1e-300) + lB[:, obs[0]]
    ptr = np.zeros((T, K), dtype=np.intp)
    for t in range(1, T):
        m = d[:, None] + lA
        ptr[t] = m.argmax(0)
        d = m.max(0) + lB[:, obs[t]]
    path = np.empty(T, dtype=np.intp)
    path[-1] = d.argmax()
    for t in range(T - 1, 0, -1):
        path[t - 1] = ptr[t, path[t]]
    return path


# ---- the statistic the hidden layer exists to explain -------------------------

def return_rate(seqs):
    """A -> B -> back-to-A rate over genuine switches (study section 7)."""
    hits = n = 0
    for s in seqs:
        for i in range(len(s) - 2):
            a, b, c = s[i], s[i + 1], s[i + 2]
            if b != a:
                n += 1
                hits += (c == a)
    return (hits / n if n else float("nan")), n


def sample(pi, A, B, lengths, rng):
    cA, cB, cpi = A.cumsum(1), B.cumsum(1), pi.cumsum()
    out = []
    for T in lengths:
        z = int(np.searchsorted(cpi, rng.random()))
        s = np.empty(T, dtype=np.intp)
        for t in range(T):
            s[t] = np.searchsorted(cB[z], rng.random())
            if t + 1 < T:
                z = int(np.searchsorted(cA[z], rng.random()))
        out.append(s)
    return out


def first_order_rate(seqs, lengths, rng, reps=5):
    M = len(MODES)
    C = np.zeros((M, M))
    for s in seqs:
        for a, b in zip(s[:-1], s[1:]):
            C[a, b] += 1
    P = C / np.maximum(C.sum(1, keepdims=True), 1e-300)
    start = np.bincount([s[0] for s in seqs], minlength=M).astype(float)
    start /= start.sum()
    cP, cs = P.cumsum(1), start.cumsum()
    rates = []
    for _ in range(reps):
        gen = []
        for T in lengths:
            s = np.empty(T, dtype=np.intp)
            s[0] = np.searchsorted(cs, rng.random())
            for t in range(1, T):
                s[t] = np.searchsorted(cP[s[t - 1]], rng.random())
            gen.append(s)
        rates.append(return_rate(gen)[0])
    return float(np.mean(rates))


# ---- naming and reporting ----------------------------------------------------

def name_states(B):
    """Read each state off its emission distribution.

    A state is named for the mode it emits most, with a rank suffix when two
    states share a dominant mode (the corpus is dialogue-dominated, so that
    happens). Names are descriptive labels for humans, not part of the model.
    """
    dominant = B.argmax(1)
    names, seen = [], {}
    for k in range(len(B)):
        base = MODES[dominant[k]]
        seen[base] = seen.get(base, 0) + 1
        names.append(base if list(dominant).count(dominant[k]) == 1
                     else f"{base}_{seen[base]}")
    return names


def state_stats(seqs, pi, A, B):
    """Viterbi-decoded dwell lengths and share per state."""
    K = len(pi)
    runs = {k: [] for k in range(K)}
    occupancy = np.zeros(K)
    for obs in seqs:
        path = viterbi(obs, pi, A, B)
        cur, n = path[0], 1
        for z in path[1:]:
            occupancy[z] += 1
            if z == cur:
                n += 1
            else:
                runs[int(cur)].append(n)
                cur, n = z, 1
        runs[int(cur)].append(n)
        occupancy[path[0]] += 1
    return runs, occupancy / occupancy.sum()


def dump_json(path, pi, A, B, names, runs, share, meta):
    """Emit the induced scene layer for the grammar file."""
    out = {
        "source": "HMM induced from nd1 block sequences by "
                  "scripts/scene_layer_hmm.py",
        "n_states": len(pi),
        "modes": MODES,
        "states": [
            {
                "name": names[k],
                "entry": float(pi[k]),
                "share": float(share[k]),
                "emission": {m: float(B[k, i]) for i, m in enumerate(MODES)},
                "transition": {names[j]: float(A[k, j])
                               for j in range(len(pi))},
                "dwell": {
                    "mean": float(np.mean(runs[k])) if runs[k] else 0.0,
                    "median": float(np.median(runs[k])) if runs[k] else 0.0,
                    "n": len(runs[k]),
                },
            }
            for k in range(len(pi))
        ],
    }
    out.update(meta)
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path}")
    return out


def report(pi, A, B, names, runs, share):
    K = len(pi)
    print(f"\n## Induced scene layer, K={K}\n")
    head = "".join(f"{m[:4]:>7}" for m in MODES)
    print(f"{'state':<16}{'entry':>7}{'share':>7}{'dwell':>7}  emission{head}")
    for k in range(K):
        d = np.mean(runs[k]) if runs[k] else 0.0
        em = "".join(f"{B[k, i]:>7.3f}" for i in range(len(MODES)))
        print(f"{names[k]:<16}{pi[k]:>7.3f}{share[k]:>7.3f}{d:>7.1f}"
              f"          {em}")
    print(f"\nstate transitions (row = from):\n")
    print(f"{'':<16}" + "".join(f"{n[:6]:>9}" for n in names))
    for k in range(K):
        print(f"{names[k]:<16}" + "".join(f"{A[k, j]:>9.3f}"
                                          for j in range(K)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, help="fit this state count and report")
    ap.add_argument("--k-range", default="2,11",
                    help="selection sweep bounds, inclusive-exclusive")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--include-giants", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()

    books = load_sequences(args.include_giants)
    names_b = sorted(books)
    allseq = [s for b in names_b for s in books[b]]
    lengths = [len(s) for s in allseq]
    obs_rate, obs_n = return_rate(allseq)
    rng = np.random.default_rng(0)
    print(f"{len(names_b)} books, {len(allseq)} units, {sum(lengths)} blocks")
    print(f"observed return rate {obs_rate:.3f} (n={obs_n:,}); "
          f"first-order simulation {first_order_rate(allseq, lengths, rng):.3f}\n")

    test_books = set(names_b[::4])
    train = [s for b in names_b if b not in test_books for s in books[b]]
    test = [s for b in names_b if b in test_books for s in books[b]]
    n_tr, n_te = sum(len(s) for s in train), sum(len(s) for s in test)

    if args.k:
        ks = [args.k]
    else:
        lo, hi = (int(x) for x in args.k_range.split(","))
        ks = list(range(lo, hi))

    chosen = None
    print(f"{'K':>3}{'train ll/blk':>14}{'test ll/blk':>13}"
          f"{'return rate':>13}{'gap':>8}")
    for K in ks:
        pi, A, B, ll, _ = best_fit(train, K, seeds=args.seeds,
                                   iters=args.iters)
        rate = float(np.mean([return_rate(sample(pi, A, B, lengths, rng))[0]
                              for _ in range(5)]))
        te = loglik(test, pi, A, B) / n_te
        print(f"{K:>3}{ll / n_tr:>14.4f}{te:>13.4f}{rate:>13.3f}"
              f"{rate - obs_rate:>+8.3f}")
        chosen = (K, pi, A, B, te, rate)

    if args.report or args.json:
        K, pi, A, B, te, rate = chosen
        names = name_states(B)
        runs, share = state_stats(allseq, pi, A, B)
        if args.report:
            report(pi, A, B, names, runs, share)
        if args.json:
            dump_json(args.json, pi, A, B, names, runs, share, {
                "n_books": len(names_b),
                "n_units": len(allseq),
                "n_blocks": int(sum(lengths)),
                "held_out_ll_per_block": te,
                "return_rate": {"masters": obs_rate, "sampled": rate},
            })


if __name__ == "__main__":
    main()

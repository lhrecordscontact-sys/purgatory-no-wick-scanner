"""Research-only champion/challenger experiments. Training-only selection.

Keep a provisional champion and a persistent registry of tested parameter
signatures so scheduled batches do not regenerate identical experiments.
No holdout metric is used for candidate generation or promotion.
"""
import json
from hashlib import sha256

CHAMPION_NAME = "champion_momentum_break_rr_1p0"
CHAMPION_PARAMS = {"signal_mode": "momentum_break", "rr": 1.0}

def signature(params):
    return sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

def propose(previous, base_variants, limit=8):
    """Mutate the fixed champion, never chase each batch's training winner."""
    champion = dict(base_variants[CHAMPION_NAME])
    seen = set(previous.get("experiment_signatures_seen", []))
    # Include previous adaptive variants even when upgrading older reports.
    seen.update(signature(p) for p in previous.get("adaptive_experiments", {}).values())
    seen.update(signature(p) for p in base_variants.values())
    # Deterministic one-factor-at-a-time sweep, rotating past tested settings.
    axes = (
        ("rr", (0.75, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)),
        ("min_rvol", (0.8, 1.0, 1.3, 1.5, 1.8, 2.0)),
        ("min_adx", (14.0, 16.0, 20.0, 22.0, 25.0, 28.0)),
        ("max_entry_extension_atr", (0.5, 0.75, 1.0, 1.25, 1.5)),
        ("min_confirmation_body", (0.5, 0.6, 0.65, 0.7, 0.75)),
        ("stop_atr_buffer", (0.1, 0.2, 0.25, 0.35, 0.5)),
    )
    candidates = {}
    for field, values in axes:
        for value in values:
            if champion.get(field) == value:
                continue
            trial = {**champion, field: value}
            key = signature(trial)
            if key in seen:
                continue
            name = "challenge_" + field + "_" + str(value).replace(".", "p")
            candidates[name] = trial
            seen.add(key)
            if len(candidates) >= limit:
                return candidates
    return candidates

def train_rank(report, minimum_trades=30):
    ranked=[]
    for name, value in report.get("results",{}).items():
        m=value.get("train",{})
        n=int(m.get("trades",0))
        if n<minimum_trades:
            continue
        net=float(m.get("net_profit",0))
        pf=m.get("profit_factor")
        if net>0 and pf is not None and float(pf)>1:
            ranked.append({"name":name,"train_trades":n,"train_net":net,
                           "train_profit_factor":pf,"net_per_trade":round(net/n,4)})
    return sorted(ranked,key=lambda x:(x["net_per_trade"],x["train_trades"]),reverse=True)

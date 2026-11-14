import datetime as dt

def apportion(n, weights):
    """Largest-remainder allocation of n items across weighted labels (exact totals)."""
    tot = sum(weights.values())
    if tot <= 0 or n <= 0:
        return {k: 0 for k in weights}
    raw = {k: n * w / tot for k, w in weights.items()}
    base = {k: int(v) for k, v in raw.items()}
    rem = n - sum(base.values())
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True)[:rem]:
        base[k] += 1
    return base

def labels_by_quota(rng, n, weights):
    counts = apportion(n, weights)
    out = [k for k, c in counts.items() for _ in range(c)]
    rng.shuffle(out)
    return out

def month_str(start, idx):
    y, m = divmod(start[0] * 12 + (start[1] - 1) + idx, 12)
    return f"{y:04d}-{m + 1:02d}"

def month_start_date(start, idx):
    y, m = divmod(start[0] * 12 + (start[1] - 1) + idx, 12)
    return dt.date(y, m + 1, 1)

def date_to_idx(start, d):
    return (d.year - start[0]) * 12 + (d.month - start[1])

def wchoice(rng, weights):
    ks = list(weights)
    return rng.choices(ks, weights=[weights[k] for k in ks])[0]

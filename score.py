def weighted_consensus(signals):
    totals = {"LONG": 0.0, "SHORT": 0.0, "NO_TRADE": 0.0}
    for signal in signals:
        direction = signal.get("direction", "NO_TRADE")
        totals[direction] += float(signal.get("weight", 1.0))
    direction = max(totals, key=totals.get)
    total = sum(totals.values()) or 1.0
    return {
        "direction": direction,
        "score": totals[direction] / total,
        "totals": totals,
    }

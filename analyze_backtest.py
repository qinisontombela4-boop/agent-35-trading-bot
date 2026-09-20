"""
Reads backtest_results.json (produced by backtest.py) and tells you which
confluence factors are actually correlated with winning trades versus which
are dead weight — or worse, correlated with losses.

Usage:
    python analyze_backtest.py backtest_results.json

IMPORTANT ON OVERFITTING: with a modest sample size (which most backtests
will have — real high-impact setups don't happen thousands of times a
month), any per-factor split can look like a strong edge purely from noise.
This script therefore does a chronological 70/30 train/test split and only
calls a factor's edge "held up" if it appears in BOTH halves in the same
direction. Don't trust a factor's edge from the train split alone — that's
exactly how people accidentally curve-fit a backtest into fool's gold.
"""

import sys, json
from datetime import datetime

FACTOR_KEYS = [
    "daily_bias", "h4_aligned", "rsi_pullback", "bos_or_breakout",
    "h1_fvg", "m5_fvg", "h1_ob", "m5_ob", "multi_ob", "h1_sweep", "m5_sweep",
]


def win_rate(trades):
    resolved = [t for t in trades if t["outcome"] in ("WIN", "LOSS")]
    if not resolved: return None, 0
    wins = sum(1 for t in resolved if t["outcome"] == "WIN")
    return round(wins / len(resolved) * 100, 1), len(resolved)


def split_by_factor(trades, factor_key):
    with_factor, without_factor = [], []
    for t in trades:
        f = t.get("factors", {})
        val = f.get(factor_key)
        # zone is a string ("discount"/"premium"/"mid"/"none"), not bool
        present = bool(val) if factor_key != "zone" else val in ("discount", "premium")
        (with_factor if present else without_factor).append(t)
    return with_factor, without_factor


def analyze(trades):
    print(f"\nTotal signals: {len(trades)}")
    overall_wr, overall_n = win_rate(trades)
    if overall_wr is None:
        print("No resolved (WIN/LOSS) trades to analyze — did any trades finish?")
        return
    print(f"Overall win rate: {overall_wr}% (n={overall_n})\n")

    # Chronological 70/30 split for an out-of-sample sanity check
    sorted_trades = sorted(trades, key=lambda t: t["time"])
    split_idx = int(len(sorted_trades) * 0.7)
    train, test = sorted_trades[:split_idx], sorted_trades[split_idx:]
    train_wr, train_n = win_rate(train)
    test_wr, test_n = win_rate(test)
    print(f"Chronological split: train={train_n} trades ({train_wr}% WR), test={test_n} trades ({test_wr}% WR)")
    print("(If these two numbers are wildly different, the strategy's edge may not be stable — treat conclusions below cautiously.)\n")

    print(f"{'FACTOR':<18}{'WITH it':<16}{'WITHOUT it':<16}{'EDGE':<10}{'HOLDS OUT-OF-SAMPLE?'}")
    print("-" * 80)
    suggestions = []
    for key in FACTOR_KEYS:
        with_f, without_f = split_by_factor(trades, key)
        wr_with, n_with = win_rate(with_f)
        wr_without, n_without = win_rate(without_f)
        if wr_with is None or wr_without is None or n_with < 5:
            print(f"{key:<18}{'insufficient data':<16}")
            continue
        edge = round(wr_with - wr_without, 1)

        # check the same edge direction holds in both train and test slices
        train_with, _ = split_by_factor(train, key)
        test_with, _ = split_by_factor(test, key)
        train_wr_f, train_n_f = win_rate(train_with)
        test_wr_f, test_n_f = win_rate(test_with)
        holds = "?"
        if train_wr_f is not None and test_wr_f is not None and train_n_f >= 3 and test_n_f >= 3:
            same_direction = (train_wr_f >= overall_wr) == (test_wr_f >= overall_wr) == (edge > 0)
            holds = "YES" if same_direction else "NO — inconsistent"

        print(f"{key:<18}{f'{wr_with}% (n={n_with})':<16}{f'{wr_without}% (n={n_without})':<16}{edge:+.1f}pp   {holds}")

        if holds == "YES" and abs(edge) >= 8:
            direction = "increase" if edge > 0 else "decrease"
            suggestions.append((key, direction, edge))

    if suggestions:
        print("\nSuggested weight adjustments (edge held up out-of-sample, |edge| >= 8pp):")
        weights_out = {}
        for key, direction, edge in suggestions:
            mult = 1.3 if direction == "increase" else 0.7
            weights_out[key] = mult
            print(f"  {key}: {direction} weight (try multiplier {mult}) — {edge:+.1f}pp win-rate edge")
        with open("suggested_weights.json", "w") as f:
            json.dump(weights_out, f, indent=2)
        print("\nWritten to suggested_weights.json — try re-running backtest.py with")
        print("  --weights-file suggested_weights.json")
        print("and compare the result to this run. Don't apply this to the live bot")
        print("until it's validated against a DIFFERENT time period than what you just")
        print("tuned on — tuning and validating on the same data is how backtests lie.")
    else:
        print("\nNo factor showed a strong, out-of-sample-consistent edge worth adjusting.")
        print("This itself is useful information: it suggests the current weights aren't")
        print("obviously miscalibrated relative to what this data shows — the win rate")
        print("issue (if any) may be more about the min_score threshold, market")
        print("conditions during this period, or risk/reward settings than about which")
        print("individual factors are weighted how.")

    # Score-bucket breakdown
    print("\nWin rate by score bucket:")
    for bucket_min, bucket_max, label in [(5,5.9,"5"),(6,6.9,"6"),(7,7.9,"7"),(8,10,"8-10")]:
        bucket = [t for t in trades if bucket_min <= t.get("score",0) <= bucket_max]
        wr, n = win_rate(bucket)
        if n: print(f"  Score {label}: {wr}% (n={n})")

    # Symbol breakdown
    print("\nWin rate by symbol:")
    symbols = sorted(set(t["symbol"] for t in trades))
    for sym in symbols:
        wr, n = win_rate([t for t in trades if t["symbol"]==sym])
        if n: print(f"  {sym}: {wr}% (n={n})")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_backtest.py backtest_results.json")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    trades = data.get("trades", data if isinstance(data, list) else [])
    analyze(trades)


if __name__ == "__main__":
    main()

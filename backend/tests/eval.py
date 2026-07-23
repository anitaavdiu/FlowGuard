"""
Scorer accuracy eval against hand-labeled sessions.

I went back through my notes from a few recent coding sessions and
labeled each one as either "overloaded" (I was genuinely confused /
stuck) or "not_overloaded" (normal work, even if busy). Then ran the
scorer against the telemetry numbers I remembered or reconstructed.

This doesn't use EWMA — each case is treated as a steady-state
snapshot, which is a reasonable proxy since the EWMA converges to
the instant score after a few minutes of consistent behavior.

Run with:
    pytest tests/eval.py -v
or:
    python tests/eval.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scorer import classify, instant_score

# Each case: raw telemetry I logged or reconstructed, a ground-truth label,
# and a short note about what was actually happening during that window.
LABELED_SESSIONS = [
    # --- sessions I'd call genuinely overloaded ---
    {
        "backspaceCount": 52,
        "fileSwitchCount": 3,
        "errorCount": 4,
        "label": "overloaded",
        "note": "fighting a TypeScript type error for 20 minutes, kept rewriting the same function",
    },
    {
        "backspaceCount": 38,
        "fileSwitchCount": 9,
        "errorCount": 2,
        "label": "overloaded",
        "note": "first time touching the auth module, bouncing between files trying to understand the flow",
    },
    {
        "backspaceCount": 45,
        "fileSwitchCount": 6,
        "errorCount": 7,
        "label": "overloaded",
        "note": "merge conflict in a file I didn't write, half the imports were broken",
    },
    {
        "backspaceCount": 61,
        "fileSwitchCount": 4,
        "errorCount": 3,
        "label": "overloaded",
        "note": "async/await bug that only showed up in prod, rewrote the same function three times",
    },
    {
        "backspaceCount": 20,
        "fileSwitchCount": 6,
        "errorCount": 3,
        "label": "overloaded",
        "note": "stuck but patient — not deleting much, just staring at the same error on repeat",
    },
    # --- sessions that felt fine ---
    {
        "backspaceCount": 8,
        "fileSwitchCount": 1,
        "errorCount": 0,
        "label": "not_overloaded",
        "note": "writing a new API endpoint in familiar territory, proper flow state",
    },
    {
        "backspaceCount": 3,
        "fileSwitchCount": 2,
        "errorCount": 0,
        "label": "not_overloaded",
        "note": "reading through codebase before a PR review, barely typing",
    },
    {
        "backspaceCount": 15,
        "fileSwitchCount": 2,
        "errorCount": 1,
        "label": "not_overloaded",
        "note": "writing unit tests — some back-and-forth but I knew exactly what I was doing",
    },
    {
        "backspaceCount": 22,
        "fileSwitchCount": 4,
        "errorCount": 2,
        "label": "not_overloaded",
        "note": "normal coding session, nothing remarkable",
    },
    {
        "backspaceCount": 42,
        "fileSwitchCount": 8,
        "errorCount": 0,
        "label": "not_overloaded",
        "note": "pair programming — high file switching but collaborative and focused, zero errors",
    },
]


def run_eval() -> None:
    tp, fp, fn, tn = 0, 0, 0, 0
    misses = []

    for case in LABELED_SESSIONS:
        score = instant_score(
            case["backspaceCount"],
            case["fileSwitchCount"],
            case["errorCount"],
        )
        predicted = classify(score)
        predicted_overloaded = predicted == "OVERLOADED"
        actually_overloaded = case["label"] == "overloaded"

        if predicted_overloaded and actually_overloaded:
            tp += 1
            outcome = "TP"
        elif predicted_overloaded and not actually_overloaded:
            fp += 1
            outcome = "FP"
        elif not predicted_overloaded and actually_overloaded:
            fn += 1
            outcome = "FN"
        else:
            tn += 1
            outcome = "TN"

        if outcome in ("FP", "FN"):
            misses.append((outcome, score, predicted, case))

    total = tp + fp + fn + tn
    correct = tp + tn

    print(f"\n{'='*55}")
    print(f"  FlowGuard scorer eval — {total} hand-labeled sessions")
    print(f"{'='*55}")
    print(f"  Correct:         {correct}/{total}")
    print(f"  True positives:  {tp}  (overloaded, caught)")
    print(f"  True negatives:  {tn}  (fine, left alone)")
    print(f"  False positives: {fp}  (fine, flagged anyway)")
    print(f"  False negatives: {fn}  (overloaded, missed)")

    if misses:
        print(f"\n  Misclassified:")
        for outcome, score, predicted, case in misses:
            print(f"    [{outcome}] score={score:.1f} → {predicted}")
            print(f"         label={case['label']}")
            print(f"         \"{case['note']}\"")

    print(f"{'='*55}\n")


if __name__ == "__main__":
    run_eval()


# also runnable as a pytest test so it shows up in the test suite
def test_eval_accuracy():
    """Scorer should be right on at least 7/10 hand-labeled sessions."""
    correct = 0
    for case in LABELED_SESSIONS:
        score = instant_score(
            case["backspaceCount"],
            case["fileSwitchCount"],
            case["errorCount"],
        )
        predicted_overloaded = classify(score) == "OVERLOADED"
        actually_overloaded = case["label"] == "overloaded"
        if predicted_overloaded == actually_overloaded:
            correct += 1
    assert correct >= 7, f"only {correct}/10 correct — scorer needs recalibration"

# Spike ceilings calibrated against the 60-second telemetry window in extension.ts.
BACKSPACE_SPIKE_THRESHOLD = 40
FILE_SWITCH_SPIKE_THRESHOLD = 8
ERROR_SPIKE_THRESHOLD = 5

EWMA_ALPHA = 0.4  # higher = new samples move the score faster
FLOW_UPPER_BOUND = 30
OVERLOADED_LOWER_BOUND = 70


def instant_score(backspace_count: int, file_switch_count: int, error_count: int) -> float:
    """Map one telemetry window to a 0-100 raw cognitive-load sample.

    Weights reflect observed impact on focus: deletions hurt most, then
    context switching, then ambient error count.
    """
    return (
        min(backspace_count / BACKSPACE_SPIKE_THRESHOLD, 1.0) * 55
        + min(file_switch_count / FILE_SWITCH_SPIKE_THRESHOLD, 1.0) * 30
        + min(error_count / ERROR_SPIKE_THRESHOLD, 1.0) * 15
    )


def apply_ewma(current: float, new_sample: float) -> float:
    return (EWMA_ALPHA * new_sample) + ((1 - EWMA_ALPHA) * current)


def classify(score: float) -> str:
    if score < FLOW_UPPER_BOUND:
        return "FLOW"
    if score < OVERLOADED_LOWER_BOUND:
        return "NORMAL"
    return "OVERLOADED"

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from scorer import apply_ewma, classify, instant_score


# instant_score -----------------------------------------------------------

def test_instant_score_all_zero():
    assert instant_score(0, 0, 0) == 0.0


def test_instant_score_at_spike_ceilings():
    # hitting all three thresholds exactly should give 100
    assert instant_score(40, 8, 5) == pytest.approx(100.0)


def test_instant_score_above_ceiling_still_caps():
    # going way over the backspace threshold shouldn't push past 55
    assert instant_score(999, 0, 0) == pytest.approx(55.0)


def test_instant_score_partial():
    # half the backspace threshold → 27.5, nothing else
    assert instant_score(20, 0, 0) == pytest.approx(27.5)


def test_instant_score_errors_only():
    assert instant_score(0, 0, 5) == pytest.approx(15.0)


# apply_ewma --------------------------------------------------------------

def test_ewma_from_zero():
    # first real sample from a cold start: α=0.4, so 0.4 * 50 = 20
    assert apply_ewma(0.0, 50.0) == pytest.approx(20.0)


def test_ewma_converges_to_constant_input():
    score = 0.0
    for _ in range(200):
        score = apply_ewma(score, 80.0)
    assert score == pytest.approx(80.0, abs=0.01)


def test_ewma_drops_when_input_falls():
    score = 80.0
    for _ in range(200):
        score = apply_ewma(score, 0.0)
    assert score == pytest.approx(0.0, abs=0.01)


def test_ewma_does_not_overshoot():
    # a single spike shouldn't push a calm baseline past the spike value
    score = apply_ewma(10.0, 100.0)
    assert score <= 100.0


# classify ----------------------------------------------------------------

def test_classify_flow_boundaries():
    assert classify(0.0) == "FLOW"
    assert classify(29.9) == "FLOW"


def test_classify_normal_boundaries():
    assert classify(30.0) == "NORMAL"
    assert classify(69.9) == "NORMAL"


def test_classify_overloaded_boundaries():
    assert classify(70.0) == "OVERLOADED"
    assert classify(100.0) == "OVERLOADED"


def test_classify_exact_thresholds_are_not_flow():
    assert classify(30.0) != "FLOW"
    assert classify(70.0) != "NORMAL"

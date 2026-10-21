"""The confidence gate learns its threshold from the recogniser's own mistakes."""
import json

from haanji.bhasha.calibration import Calibration, fit_threshold, labelled_tokens, roc
from haanji.collect import Pair


def pairs():
    # Right words carry high confidence, wrong words low: a threshold near 0.6 separates them.
    out = []
    for i in range(30):
        out.append(Pair("p", "mujhe root canal karwana hai", "mujhe rut canal karwana hai",
                        [0.95, 0.40 + (i % 5) * 0.03, 0.9, 0.93, 0.97]))
        out.append(Pair("p", "kal subah ka time", "kal subah ka taim", [0.9, 0.88, 0.92, 0.55]))
    return out


def test_tokens_are_labelled_by_alignment():
    pts = labelled_tokens(pairs()[:1])
    assert len(pts) == 5 and [w for _, w in pts] == [False, True, False, False, False]
    assert labelled_tokens([Pair("p", "a b", "a b", [0.9])]) == [], "confidences that do not align are skipped"


def test_fit_finds_the_separating_threshold():
    fit = fit_threshold(pairs())
    assert 0.55 < fit["threshold"] <= 0.9 and fit["tpr"] == 1.0 and fit["fpr"] == 0.0 and fit["auc"] > 0.99
    assert fit["tokens"] == 270 and fit["wrong_tokens"] == 60
    assert fit_threshold([])["threshold"] == 0.85


def test_roc_is_monotone():
    curve = roc(labelled_tokens(pairs()))
    tprs = [c["tpr"] for c in curve]
    assert tprs == sorted(tprs) and curve[0]["tpr"] == 0.0 and curve[-1]["tpr"] == 1.0


def test_calibration_table_matches_by_prefix(tmp_path):
    p = tmp_path / "calibration.json"
    p.write_text(json.dumps({"recognisers": {"faster-whisper:small:en": {"threshold": 0.62},
                                             "faster-whisper:small:hi": {"threshold": 0.71}}}))
    c = Calibration.load(p)
    assert c.threshold_for("faster-whisper:small:en:biased") == 0.62
    assert c.threshold_for("faster-whisper:small:hi") == 0.71
    assert c.threshold_for("deepgram:nova-2") == 0.85 and c.threshold_for(None) == 0.85
    assert Calibration.load(tmp_path / "missing.json", 0.8).threshold_for("x") == 0.8

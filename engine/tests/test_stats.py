"""The report's significance tests, checked against values a textbook table gives."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "harness"))
import stats  # noqa: E402


def test_t_distribution_tail_matches_tables():
    assert abs(stats.t_sf(2.776, 4) - 0.05) < 0.002          # t_{0.025, 4} = 2.776
    assert abs(stats.t_sf(1.96, 1000) - 0.05) < 0.002
    assert abs(stats.t_sf(12.706, 1) - 0.05) < 0.002


def test_chi_square_one_df_tail_matches_tables():
    assert abs(stats.chi2_1_sf(3.841) - 0.05) < 0.001
    assert abs(stats.chi2_1_sf(6.635) - 0.01) < 0.001


def test_mcnemar_and_paired_t():
    m = stats.mcnemar(b=40, c=5)
    assert m["n_discordant"] == 45 and m["statistic"] == round((34 ** 2) / 45, 3) and m["p"] < 0.001
    assert stats.mcnemar(0, 0)["p"] == 1.0
    t = stats.paired_t([1.0, 1.2, 0.9, 1.1, 1.0])
    assert t["df"] == 4 and t["p"] < 0.001 and abs(t["mean"] - 1.04) < 1e-9
    assert stats.paired_t([0.0, 0.0, 0.0])["p"] == 1.0
    assert stats.fmt_p(0.0004) == "< 0.001" and stats.fmt_p(0.0421) == "= 0.042"
    assert abs(stats.cohens_d([1, 2, 3], [4, 5, 6]) + 3.0) < 1e-9

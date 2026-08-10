"""Test researcher.validate_hypothesis (#50) — findings persisted to the KnowledgeStore."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _KS:
    def __init__(self): self.stored = []
    def remember(self, **kw): self.stored.append(kw)


class _DB:
    db_path = ":memory:"
    def _account_clause(self): return "", []


def test_validate_hypothesis_stores_verdict():
    from src.learning.continual_researcher import ContinualResearcher
    ks = _KS()
    r = ContinualResearcher(_DB(), knowledge_store=ks)
    rec = r.validate_hypothesis("k1", "filters dont separate winners",
                                {"peak_gap": 3.0}, verdict="agree", confidence="medium")
    assert rec["verdict"] == "agree"
    assert r.validated_snapshot()["k1"]["claim"].startswith("filters")
    # stored to knowledge with a stable key + finding kind
    assert ks.stored and ks.stored[0]["key"] == "validated_k1"
    assert ks.stored[0]["kind"] == "finding"
    assert "AGREE" in ks.stored[0]["text"]


def test_validate_updates_in_place():
    from src.learning.continual_researcher import ContinualResearcher
    ks = _KS()
    r = ContinualResearcher(_DB(), knowledge_store=ks)
    r.validate_hypothesis("k2", "claim", {"x": 1}, "inconclusive")
    r.validate_hypothesis("k2", "claim", {"x": 2}, "disagree")  # new data overturns
    assert r.validated_snapshot()["k2"]["verdict"] == "disagree"


if __name__ == "__main__":
    test_validate_hypothesis_stores_verdict()
    test_validate_updates_in_place()
    print("validate_hypothesis tests passed")

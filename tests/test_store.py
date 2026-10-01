from concurrent.futures import ThreadPoolExecutor

from paid_media.experiments import recommendations
from paid_media.store import Conflict, Store


def test_decisions_survive_reopen_and_races_have_one_winner(tmp_path, report):
    path = tmp_path / "reviews.sqlite"
    store = Store(path)
    proposals = recommendations(report)
    store.sync(proposals)
    rid = proposals[0]["id"]

    def decide(status):
        try:
            store.transition(rid, status, "Human analyst", "Reviewed proposal", 1)
            return "saved"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ["Approved", "Rejected"]))
    assert sorted(results) == ["conflict", "saved"]
    reopened = Store(path)
    reopened.sync(proposals)
    assert reopened.get(rid)["version"] == 2
    assert reopened.get(rid)["status"] in {"Approved", "Rejected"}
    assert len(reopened.history(rid)) == 1

from feed.diff import build_snapshot, compute_diff
from feed.models import Job, SourceResult


def job(source, jid, title="Intern", desc="d"):
    return Job(source=source, company=source, job_id=jid, title=title, location="NYC",
               date_posted="2026-11-01", apply_url="https://x/" + jid, description=desc)


def snap(*jobs):
    return {"jobs": {j.key: j.to_record() for j in jobs}}


def res(name, complete=True):
    return SourceResult(name, name, scope="s", complete=complete)


def test_new_closed_changed():
    old = snap(job("a", "1"), job("a", "2"), job("a", "3", title="Old title"))
    now = [job("a", "1"), job("a", "3", title="New title"), job("a", "4")]
    d = compute_diff(old, now, [res("a")])
    assert d["new"] == ["a:4"]
    assert d["closed"] == ["a:2"]
    assert list(d["changed"]) == ["a:3"] and "title" in d["changed"]["a:3"]


def test_description_edit_counts_as_changed():
    old = snap(job("a", "1", desc="v1"))
    d = compute_diff(old, [job("a", "1", desc="v2")], [res("a")])
    assert "description_hash" in d["changed"]["a:1"]


def test_incomplete_source_never_reports_closed():
    old = snap(job("a", "1"), job("b", "9"))
    d = compute_diff(old, [job("a", "1")], [res("a"), res("b", complete=False)])
    assert d["closed"] == []
    assert d["carried_over_incomplete_source"] == ["b:9"]
    assert "b:9" in build_snapshot(old, [job("a", "1")], d, "t")["jobs"]   # kept for next run


def test_first_run():
    d = compute_diff({}, [job("a", "1")], [res("a")])
    assert d["first_run"] and d["new"] == ["a:1"]

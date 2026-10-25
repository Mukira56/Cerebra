"""Before/after test evidence: failing test names from common runners, and verdicts that never overclaim."""
import pytest

from ai_hq.evidence import compare, failing_tests, summarize


@pytest.mark.parametrize("output,names", [
    ("FAILED tests/test_calc.py::test_add - assert 1 == 5\nERROR tests/test_db.py::test_open\n", ["tests/test_calc.py::test_add", "tests/test_db.py::test_open"]),
    ("FAIL: test_add (test_calc.CalcTest.test_add)\nERROR: test_io (test_io.IOTest.test_io)\n", ["test_calc.CalcTest.test_add.test_add", "test_io.IOTest.test_io.test_io"]),
    ("  ✓ subtracts (1 ms)\n  ✕ adds numbers (3 ms)\n", ["adds numbers"]),
    ("--- FAIL: TestAdd (0.00s)\n--- PASS: TestSub (0.00s)\n", ["TestAdd"]),
    ("test calc::adds ... FAILED\ntest calc::subs ... ok\n", ["calc::adds"]),
    ("  Failed Calc.Tests.AddWorks [12 ms]\n", ["Calc.Tests.AddWorks"]),
    ("everything is fine\n", []),
])
def test_failing_test_names_from_common_runners(output, names):
    assert failing_tests(output) == names


def run(passed, output=""):
    return {"command": ["pytest"], "passed": passed, "exit_code": 0 if passed else 1, "stdout": output, "stderr": "", "attempt": 0}


BROKEN = summarize([run(False, "FAILED t.py::test_add\n")])
HEALTHY = summarize([run(True)])


@pytest.mark.parametrize("baseline,after,verdict", [
    (BROKEN, [run(True)], "fixed"),
    (HEALTHY, [run(True)], "still_passing"),
    (BROKEN, [run(False, "FAILED t.py::test_add\n")], "still_failing"),
    (HEALTHY, [run(False, "FAILED t.py::test_new\n")], "broke"),
])
def test_verdicts(baseline, after, verdict):
    result = compare(baseline, after)
    assert result["verdict"] == verdict
    if verdict == "still_passing":
        assert "don't prove" in result["text"]  # passing tests that also passed before aren't proof of the change
    if verdict == "broke":
        assert result["newly_failing"] == ["t.py::test_new"]


def test_only_the_latest_attempt_counts_and_missing_baseline_is_stated():
    attempts = [dict(run(False, "FAILED t.py::test_add\n"), attempt=0), dict(run(True), attempt=1)]
    assert compare(BROKEN, attempts)["verdict"] == "fixed"
    assert compare(BROKEN, [])["verdict"] == "not_yet"
    assert compare(None, attempts) == {"available": False, "text": compare(None, [])["text"]}

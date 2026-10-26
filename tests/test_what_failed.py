"""What failed: the part of a test run that explains the failure, found even under pages of repeated warnings.
The owner's EstatePilot task ran out of repairs because only the output's tail was kept, and the tail was 20 copies
of one Node warning; the real cause (sign-up returning 503) was further up."""
from ai_hq.evidence import failing_tests, what_failed
from test_supervisor import WrongAgentRegistry, hq, ready  # noqa: F401  (hq is a fixture)

WARNING = ("(node:16464) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.\n"
           "(Use `node --trace-warnings ...` to show where the warning was created)\n")
PLAYWRIGHT = ("Running 15 tests using 2 workers\n"
              "  ok 1 [desktop-chromium] › tests/e2e/foundation.spec.ts:28:1 › planned workflows expand (6.0s)\n"
              "  1) [desktop-chromium] › tests/e2e/access.spec.ts:178:1 › verified accounts keep household access isolated\n"
              "    Error: expect(received).toBe(expected) // Object.is equality\n"
              "    Expected: 200\n"
              "    Received: 503\n"
              "    > 136 |   expect((await signUp).status()).toBe(200);\n"
              "        at node:internal/process/task_queues:105:5\n"
              + WARNING * 20 +
              "  1 failed\n  10 passed (56.8s)\n")


def test_the_failure_is_found_under_repeated_warnings():
    text = what_failed(PLAYWRIGHT)
    assert "Received: 503" in text and "access.spec.ts:178:1" in text and "1 failed" in text
    assert "NO_COLOR" not in text and "node:internal" not in text
    assert PLAYWRIGHT.strip()[-1500:].count("NO_COLOR") > 5  # what the old tail showed instead
    assert failing_tests(PLAYWRIGHT) == ["tests/e2e/access.spec.ts:178:1 › verified accounts keep household access isolated"]


def test_long_output_is_kept_short_and_still_ends_with_the_summary():
    noisy = "".join(f"  1) [chromium] › tests/case{index}.spec.ts:1:1 › case {index}\n    Error: boom {index}\n" for index in range(400)) + "  400 failed\n"
    text = what_failed(noisy, limit=2000)
    assert len(text) <= 2000 and text.endswith("400 failed") and "boom 0" in text
    assert what_failed("") == "" and what_failed(WARNING * 3) == ""


class RecordingWrongAgent(WrongAgentRegistry):
    def execute(self, name, request, cancel_event=None):
        if request.role == "implement":
            self.requests.append((name, request))
        return super().execute(name, request, cancel_event)


def test_repairs_get_what_failed_not_raw_output(hq):
    supervisor = hq[0]
    supervisor.registry = RecordingWrongAgent()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    failing = [result for result in task.test_results if not result["passed"]]
    assert failing and all(result["what_failed"] for result in failing)
    repairs = [request for name, request in supervisor.registry.requests if getattr(request, "role", "") == "implement" and request.attempt]
    assert repairs and '"what_failed"' in repairs[0].description and '"stdout"' not in repairs[0].description
    assert "assert" in repairs[0].description  # pytest's own failure line reached the coder


def test_try_again_tells_the_coder_what_still_fails(hq):
    supervisor = hq[0]
    supervisor.registry = RecordingWrongAgent()
    task_id = ready(hq)
    supervisor.run_until_idle()
    assert supervisor.get(task_id).state == "FAILED"
    before = len(supervisor.registry.requests)
    supervisor.try_again(task_id)
    supervisor.run_until_idle()
    first = next(request for name, request in supervisor.registry.requests[before:] if getattr(request, "role", "") == "implement")
    assert "Try again from where it stopped" in first.description and "What failed:" in first.description and "assert" in first.description

"""The resumable eval runner, with a fake network call. No real API calls.

Only llm._call_once (the one function that talks to Groq) is replaced, so the real cache,
usage log, JSON checks and the daily-limit stop are all exercised.
"""

import json
import types

import pytest

import config
import evaluate
import llm
import run_eval

LAW = "This Agreement is governed by the laws of Texas."
TITLES = ["c1", "c2", "c3"]


def record(title):
    # the title sits inside the Law section, so each contract's second-pass message is unique
    text = f"Agreement {title}.\n1. Term. One year.\n2. Law. For agreement {title}: {LAW}\n"
    start = text.index(LAW)
    gold = {c: [] for c in config.CATEGORIES}
    gold["Governing Law"] = [{"text": LAW, "start": start}]
    return {"title": title, "split": "test", "text": text, "gold": gold}


RECORDS = {t: record(t) for t in TITLES}


class FakeAPI:
    """Answers like the model would. After `budget` answers, raises DailyLimitReached."""

    def __init__(self, budget=None):
        self.budget, self.paid = budget, []

    def __call__(self, messages, params, estimated_tokens):
        if self.budget is not None and len(self.paid) >= self.budget:
            raise llm.DailyLimitReached("retry-after 3600s (fake)")
        key = json.dumps(messages, sort_keys=True)
        self.paid.append(key)
        if "<contract_section>" in messages[1]["content"]:
            content = {"verdict": "confirm", "reason": "states the governing law"}
        else:
            content = {"findings": [{"category": "Governing Law", "quote": LAW, "reason": "law clause"}]}
        usage = types.SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120,
                                      completion_tokens_details=None)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(
            content=json.dumps(content)))], usage=usage, model=config.MODEL)


REAL_OUTPUTS = [config.RESULTS_DIR / "eval.json", config.RESULTS_DIR / "eval_log.txt"]


@pytest.fixture(autouse=True)
def never_touch_real_results(tmp_path, monkeypatch):
    """Every test writes to tmp only; fail loudly if a real results file appears."""
    before = {p: p.exists() for p in REAL_OUTPUTS}
    monkeypatch.setattr(run_eval, "OUT", tmp_path / "default_eval.json")
    monkeypatch.setattr(run_eval, "LOG", tmp_path / "default_eval_log.txt")
    yield
    assert {p: p.exists() for p in REAL_OUTPUTS} == before, "a test wrote to the real results/ folder"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "RESPONSE_CACHE", tmp_path / "cache" / "responses")
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "cache" / "usage_log.jsonl")
    monkeypatch.setattr(llm, "_get_client", lambda: pytest.fail("real client must never be created"))
    return tmp_path / "eval.json"


def run_with(api, out, monkeypatch):
    monkeypatch.setattr(llm, "_call_once", api)
    return run_eval.run_eval(TITLES, RECORDS, out)


def test_stop_at_daily_limit_then_resume_without_repeating_paid_calls(env, monkeypatch, capsys):
    # Each contract needs 2 calls (first pass, second pass). Budget 3: c1 finishes,
    # c2's first pass is answered (and cached), then the limit hits on c2's second pass.
    first = FakeAPI(budget=3)
    data = run_with(first, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["complete"] is False and "daily limit" in info["stopped_reason"]
    assert info["finished_titles"] == ["c1"]
    assert [k["title"] for k in data["contracts"]] == ["c1"]
    assert len(first.paid) == 3
    assert "STOPPED at the daily limit" in capsys.readouterr().out
    saved = json.loads(env.read_text(encoding="utf-8"))
    assert saved["summary"]["run"]["complete"] is False          # the file on disk says so too
    with pytest.raises(evaluate.RunNotScorable, match="incomplete"):
        evaluate.score(saved)                                       # and scoring refuses it

    # Next day: c1 skipped, c2's first pass from cache, only new calls are paid.
    second = FakeAPI()
    data = run_with(second, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["complete"] is True and info["stopped_reason"] is None
    assert info["finished_titles"] == TITLES
    assert len(second.paid) == 3                                    # c2 second pass + c3 both passes
    assert not set(first.paid) & set(second.paid)                   # no paid call repeated
    assert len(info["sessions"]) == 2
    assert info["sessions"][0]["finished_this_session"] == ["c1"]
    assert info["sessions"][1]["finished_this_session"] == ["c2", "c3"]
    c2 = data["contracts"][1]
    assert c2["chunks"][0]["cached"] is True and c2["findings"][0]["second_pass_cached"] is False

    # A third run has nothing to do and pays nothing.
    third = FakeAPI(budget=0)
    data = run_with(third, env, monkeypatch)
    assert third.paid == [] and data["summary"]["run"]["complete"] is True

    # The finished file is scoreable, and the token record counts every call once.
    m = evaluate.score(data)
    gl = m["per_category"]["Governing Law"]["contract_level"]["after_second_pass"]
    assert (gl["tp"], gl["fp"], gl["fn"]) == (3, 0, 0)
    tok = data["summary"]["tokens"]
    assert tok["calls"] == {"first_pass": 3, "second_pass": 3}
    assert tok["first_pass_all_calls"]["total_tokens"] == 360


def test_limit_on_very_first_call_saves_empty_incomplete_run(env, monkeypatch):
    data = run_with(FakeAPI(budget=0), env, monkeypatch)
    assert data["summary"]["run"]["complete"] is False and data["contracts"] == []
    assert env.exists()


def test_refuses_unfrozen_prompts(env, monkeypatch):
    monkeypatch.setattr(config, "DEFINITIONS", "category_definitions_v3")
    api = FakeAPI()
    with pytest.raises(RuntimeError, match="frozen"):
        run_with(api, env, monkeypatch)
    assert api.paid == [] and not env.exists()


def test_refuses_to_resume_other_versions_or_titles(env, monkeypatch):
    run_with(FakeAPI(budget=1), env, monkeypatch)
    data = json.loads(env.read_text(encoding="utf-8"))
    data["summary"]["run"]["definitions"] = "category_definitions_v3"
    env.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="different versions"):
        run_with(FakeAPI(), env, monkeypatch)
    data["summary"]["run"]["definitions"] = run_eval.FROZEN["definitions"]
    data["summary"]["run"]["titles"] = ["other"]
    env.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="title list"):
        run_with(FakeAPI(), env, monkeypatch)


def test_plan_only_makes_no_calls(monkeypatch, capsys):
    monkeypatch.setattr(run_eval, "load_inputs", lambda: (TITLES, RECORDS))
    monkeypatch.setattr(llm, "_call_once", lambda *a: pytest.fail("no calls in plan mode"))
    run_eval.main([])
    assert "Plan only" in capsys.readouterr().out


def test_log_is_written(env, monkeypatch, tmp_path):
    log = tmp_path / "eval_log.txt"
    monkeypatch.setattr(run_eval, "load_inputs", lambda: (TITLES, RECORDS))
    monkeypatch.setattr(run_eval, "OUT", env)
    monkeypatch.setattr(run_eval, "LOG", log)
    monkeypatch.setattr(llm, "_call_once", FakeAPI(budget=1))
    run_eval.main(["--run"])
    text = log.read_text(encoding="utf-8")
    assert "eval session 1" in text and "STOPPED at the daily limit" in text


# --- connection/server failures vs invalid model replies ----------------------------------------

class FlakyAPI(FakeAPI):
    """Like FakeAPI, but attempt numbers in `fail` raise a connection error (the model never
    answers), and attempt numbers in `invalid` get an answer that is not JSON."""

    def __init__(self, fail=(), invalid=(), fail_from=None):
        super().__init__()
        self.fail, self.invalid, self.fail_from, self.attempts = set(fail), set(invalid), fail_from, 0

    def __call__(self, messages, params, estimated_tokens):
        self.attempts += 1
        n = self.attempts
        if n in self.fail or (self.fail_from is not None and n >= self.fail_from):
            raise llm.CallFailed("APIConnectionError: Connection error. (fake)")
        reply = super().__call__(messages, params, estimated_tokens)
        if n in self.invalid:
            reply.choices[0].message.content = "this is not JSON"
        return reply


FIVE = [f"k{i}" for i in range(1, 6)]
FIVE_RECORDS = {t: record(t) for t in FIVE}


def run5(api, out, monkeypatch):
    monkeypatch.setattr(llm, "_call_once", api)
    return run_eval.run_eval(FIVE, FIVE_RECORDS, out)


def test_stops_after_three_connection_failures_in_a_row_then_resumes(env, monkeypatch, capsys):
    # k1 needs 2 good calls. From attempt 3 every call fails: k2, k3 and k4 each fail once
    # (one chunk each); the third failure in a row stops the run before k5.
    api = FlakyAPI(fail_from=3)
    data = run5(api, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["complete"] is False and "connection problems" in info["stopped_reason"]
    assert info["finished_titles"] == ["k1"]
    assert api.attempts == 5                                    # k5 never tried
    s = info["sessions"][0]
    assert [x["title"] for x in s["not_finished_connection_errors"]] == ["k2", "k3"]  # k4 was abandoned mid-way
    assert "STOPPED because of connection problems" in capsys.readouterr().out
    with pytest.raises(evaluate.RunNotScorable, match="incomplete"):
        evaluate.score(json.loads(env.read_text(encoding="utf-8")))

    healthy = FakeAPI()
    data = run5(healthy, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["complete"] is True and info["finished_titles"] == FIVE
    assert len(healthy.paid) == 8                               # k2..k5, 2 calls each; k1 not repeated
    assert not set(api.paid) & set(healthy.paid)
    evaluate.score(data)                                        # scoreable now


def test_isolated_connection_failure_leaves_contract_unfinished(env, monkeypatch):
    # attempt 3 = k2's first pass fails once; everything else works, so the run goes on
    api = FlakyAPI(fail={3})
    data = run5(api, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["finished_titles"] == ["k1", "k3", "k4", "k5"]
    assert info["complete"] is False and "retry" in info["stopped_reason"]
    assert all(not k["failed_chunks"] for k in data["contracts"])   # no failed part is saved as a result

    healthy = FakeAPI()
    data = run5(healthy, env, monkeypatch)
    assert data["summary"]["run"]["complete"] is True
    assert len(healthy.paid) == 2                               # only k2 retried
    evaluate.score(data)


def test_second_pass_connection_failure_also_leaves_contract_unfinished(env, monkeypatch):
    api = FlakyAPI(fail={2})                                    # k1's second pass
    data = run5(api, env, monkeypatch)
    info = data["summary"]["run"]
    assert "k1" not in info["finished_titles"] and info["complete"] is False
    assert "second pass" in info["sessions"][0]["not_finished_connection_errors"][0]["parts"][0]


def test_invalid_model_reply_is_a_result_and_not_retried(env, monkeypatch):
    # attempts 3 and 4 = k2's first pass and its one retry, both answered with non-JSON
    api = FlakyAPI(invalid={3, 4})
    data = run5(api, env, monkeypatch)
    info = data["summary"]["run"]
    assert info["complete"] is True and info["finished_titles"] == FIVE
    k2 = data["contracts"][1]
    assert k2["failed_chunks"] == [0] and k2["errors"][0]["error"].startswith("InvalidResponse")
    assert all(c["status"] == "Needs review" for c in k2["clauses"])
    assert info["sessions"][0]["invalid_model_replies"] == 1
    m = evaluate.score(data)                                    # scored, not refused
    assert m["invalid_model_replies"]["first_pass_chunks"] == 1

    again = FakeAPI(budget=0)                                   # a rerun pays nothing: not retried
    run5(again, env, monkeypatch)
    assert again.paid == []


def test_invalid_reply_resets_the_failure_count(env, monkeypatch):
    # fail, fail, invalid (an answer), fail, fail: never 3 connection failures in a row
    api = FlakyAPI(fail={3, 4, 7, 8}, invalid={5, 6})
    data = run5(api, env, monkeypatch)
    assert "connection problems" not in (data["summary"]["run"]["stopped_reason"] or "")


def test_call_counter_is_removed_after_the_run(env, monkeypatch):
    original = llm.chat_json
    run5(FlakyAPI(fail_from=1), env, monkeypatch)       # stops with ConnectionTrouble
    assert llm.chat_json is original
    run5(FakeAPI(), env, monkeypatch)                    # completes normally
    assert llm.chat_json is original

"""Run the frozen pipeline on the eval set, resumably across days.

Run:  .venv/Scripts/python run_eval.py          shows the plan and makes NO API calls
      .venv/Scripts/python run_eval.py --run    runs (or resumes) the eval

Writes results/eval.json (same format evaluate.py scores) after EVERY finished contract,
and appends the console output to results/eval_log.txt.

Resuming:
  - Contracts already in results/eval.json are finished and are skipped (no calls at all).
  - At the daily limit (llm.DailyLimitReached) the current contract is abandoned, the run is
    saved with complete = false, and the script stops. Every API reply received before the
    stop is in the cache, so the next run redoes that contract from the cache and pays only
    for calls that never got an answer. No paid call is repeated.
  - Connection or server failures (the model never answered): after 3 in a row the run stops the
    same way. A contract with any part that failed this way is NOT finished, even if the run
    goes on, so the next run retries it (its successful calls come from the cache).
  - Invalid model replies (the model answered, but the output was unusable after one retry) are a
    real result: that part is Needs review, the contract is finished, and it is not retried.
  - complete = true only when every eval title is finished. evaluate.py refuses anything else.

Refuses to start if config.py's prompts differ from the frozen ones, or if an existing
results/eval.json was made with a different model, prompts or title list.
"""

import contextlib
import datetime as dt
import json
import sys

import config
import llm
from pipeline import analyse_contract

MAX_CALL_FAILURES_IN_A_ROW = 3  # connection or server failures (llm.CallFailed) before the run stops


class ConnectionTrouble(RuntimeError):
    """Too many connection or server failures in a row: stop the run, like the daily limit.
    Deliberately not a subclass of llm.CallFailed, so the pipeline does not catch it."""


@contextlib.contextmanager
def stop_after_call_failures_in_a_row(limit: int = MAX_CALL_FAILURES_IN_A_ROW):
    """While active, every API call goes through a counter. A connection or server failure
    (llm.CallFailed: the model never answered) adds one; any answer, including an invalid one,
    resets it. At `limit` failures in a row, ConnectionTrouble is raised and ends the contract.
    The pipeline's own code is unchanged: it calls llm.chat_json, which is wrapped here."""
    original = llm.chat_json
    in_a_row = 0

    def guarded(*args, **kwargs):
        nonlocal in_a_row
        try:
            reply = original(*args, **kwargs)
        except llm.CallFailed as e:
            in_a_row += 1
            if in_a_row >= limit:
                raise ConnectionTrouble(f"{in_a_row} connection/server failures in a row (last: {e})") from e
            raise
        except llm.InvalidResponse:
            in_a_row = 0  # the service answered; the output was unusable
            raise
        in_a_row = 0
        return reply

    llm.chat_json = guarded
    try:
        yield
    finally:
        llm.chat_json = original


def connection_failures(out: dict) -> list[str]:
    """Parts of one contract's output that failed because of a connection or server error,
    i.e. the model never answered. Such a contract is not finished and is retried on resume."""
    parts = [f"chunk {e['chunk']}" for e in out["errors"] if e["error"].startswith("CallFailed")]
    parts += [f"second pass for {f['category']} at {f['start']}-{f['end']}" for f in out["findings"]
              if (f.get("second_pass_error") or "").startswith("CallFailed")]
    return parts


def invalid_replies(out: dict) -> int:
    """Calls where the model answered but the output was unusable after one retry. These are a
    real result (the part is Needs review) and are NOT retried."""
    return (sum(e["error"].startswith("InvalidResponse") for e in out["errors"])
            + sum((f.get("second_pass_error") or "").startswith("InvalidResponse") for f in out["findings"]))

# Frozen after Stage 3 (David). Changing them means a new eval run, not a resume.
FROZEN = {"model": "openai/gpt-oss-120b", "first_pass_prompt": "first_pass_v2",
          "second_pass_prompt": "second_pass_v1", "definitions": "category_definitions_v4"}
OUT = config.RESULTS_DIR / "eval.json"
LOG = config.RESULTS_DIR / "eval_log.txt"


class Tee:
    """Send console output to the screen and a log file."""

    def __init__(self, stream, path):
        self.stream, self.file = stream, open(path, "a", encoding="utf-8")

    def write(self, s):
        self.stream.write(s)
        self.file.write(s)

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def close(self):
        self.file.close()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def current_versions(cfg=config) -> dict:
    return {"model": cfg.MODEL, "first_pass_prompt": cfg.FIRST_PASS_PROMPT,
            "second_pass_prompt": cfg.SECOND_PASS_PROMPT, "definitions": cfg.DEFINITIONS}


def check_frozen(cfg=config) -> None:
    if current_versions(cfg) != FROZEN:
        raise RuntimeError(f"config.py prompts are not the frozen ones: {current_versions(cfg)} != {FROZEN}")


def load_or_start(out_path, titles: list[str]) -> dict:
    if not out_path.exists():
        return {"summary": {"run": {**FROZEN, "titles": titles, "complete": False, "stopped_reason": None,
                                    "finished_titles": [], "sessions": []}},
                "contracts": []}
    data = json.loads(out_path.read_text(encoding="utf-8"))
    info = data["summary"]["run"]
    if {k: info.get(k) for k in FROZEN} != FROZEN:
        raise RuntimeError(f"{out_path} was made with different versions; refusing to resume it")
    if info["titles"] != titles:
        raise RuntimeError(f"{out_path} was made for a different title list; refusing to resume it")
    return data


def tokens_summary(contracts: list[dict]) -> dict:
    """Token cost of every call behind these results (cached calls count at their original cost)."""
    def tot(rows):
        return {k: sum((r or {}).get(k) or 0 for r in rows)
                for k in ("prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens")}
    fp = [ch["usage"] for k in contracts for ch in k["chunks"] if ch["status"] == "ok"]
    sp = [f["second_pass_usage"] for k in contracts for f in k["findings"] if f["second_pass_usage"]]
    return {"first_pass_all_calls": tot(fp), "second_pass_all_calls": tot(sp),
            "calls": {"first_pass": len(fp), "second_pass": len(sp)}}


def save(data: dict, out_path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out_path)  # never leave a half-written results file


def run_eval(titles: list[str], records: dict, out_path=None, cfg=config) -> dict:
    """Run or resume. Returns the saved data. Raises before any call if versions are wrong."""
    out_path = out_path or OUT  # looked up at call time, not fixed when the function is defined
    check_frozen(cfg)
    data = load_or_start(out_path, titles)
    info = data["summary"]["run"]
    done = set(info["finished_titles"])
    session = {"started": now(), "tokens_today_at_start": llm.tokens_today(),
               "finished_this_session": [], "not_finished_connection_errors": [],
               "invalid_model_replies": 0, "stopped_reason": None}
    info["sessions"].append(session)
    todo = [t for t in titles if t not in done]
    print(f"\n=== eval session {len(info['sessions'])} started {session['started']} | "
          f"{len(done)}/{len(titles)} finished, {len(todo)} to go | tokens today "
          f"{session['tokens_today_at_start']:,} / {config.TOKENS_PER_DAY:,}")

    # One counter for the whole session: failures in a row are counted across contracts, so an
    # outage stops the run even when each contract only makes one failing call.
    with stop_after_call_failures_in_a_row():
        for i, title in enumerate(todo, 1):
            rec = records[title]
            print(f"\n[{len(done) + i}/{len(titles)}] {title[:90]}")
            try:
                out = analyse_contract(rec["text"])
            except llm.DailyLimitReached as e:
                session["stopped_reason"] = f"daily limit: {e}"
                print(f"STOPPED at the daily limit: {e}\n"
                      f"Saved with complete=false. Run again later: finished contracts are skipped and "
                      f"this one is redone from the cache.")
                break
            except ConnectionTrouble as e:
                session["stopped_reason"] = f"connection problems: {e}"
                print(f"STOPPED because of connection problems: {e}\n"
                      f"Saved with complete=false. Run again later: finished contracts are skipped and "
                      f"this one is redone from the cache.")
                break
            failed_parts = connection_failures(out)
            if failed_parts:  # the model never answered for some part: not a result, retry on resume
                session["not_finished_connection_errors"].append({"title": title, "parts": failed_parts})
                print(f"  NOT FINISHED: {len(failed_parts)} part(s) failed with connection/server errors "
                      f"({'; '.join(failed_parts)}). It will be retried on the next run.")
                continue
            session["invalid_model_replies"] += invalid_replies(out)
            gold = {c: [{"start": s["start"], "end": s["start"] + len(s["text"])} for s in rec["gold"][c]]
                    for c in config.CATEGORIES}
            for f in out["findings"]:
                f["text_in_contract"] = rec["text"][f["start"]:f["end"]]
            for cl in out["clauses"]:
                print(f"  {cl['category']:28s} {cl['status']:18s} {'; '.join(cl['reasons'])}")
            data["contracts"].append({"title": title, "chars": len(rec["text"]), "gold": gold, **out})
            info["finished_titles"].append(title)
            session["finished_this_session"].append(title)
            info["complete"] = len(info["finished_titles"]) == len(titles)
            info["stopped_reason"] = None
            data["summary"]["tokens"] = tokens_summary(data["contracts"])
            save(data, out_path)

    session["finished"] = now()
    session["tokens_today_at_end"] = llm.tokens_today()
    info["complete"] = len(info["finished_titles"]) == len(titles)
    if not info["complete"] and not session["stopped_reason"] and session["not_finished_connection_errors"]:
        session["stopped_reason"] = (f"{len(session['not_finished_connection_errors'])} contract(s) had "
                                     "connection/server failures; run again to retry them")
    info["stopped_reason"] = session["stopped_reason"]
    data["summary"]["tokens"] = tokens_summary(data["contracts"])
    save(data, out_path)
    print(f"\n=== session end {session['finished']} | {len(info['finished_titles'])}/{len(titles)} finished | "
          f"complete={info['complete']} | not finished (connection) "
          f"{len(session['not_finished_connection_errors'])} | invalid model replies "
          f"{session['invalid_model_replies']} | tokens today {session['tokens_today_at_end']:,}"
          + (f"\n    stopped: {info['stopped_reason']}" if info["stopped_reason"] else ""))
    return data


def load_inputs():
    titles = json.loads(config.EVAL_TITLES_PATH.read_text(encoding="utf-8"))
    with open(config.CONTRACTS_PATH, encoding="utf-8") as f:
        records = {r["title"]: r for r in map(json.loads, f) if r["title"] in titles}
    missing = [t for t in titles if t not in records or records[t]["split"] != "test"]
    if missing:
        raise RuntimeError(f"eval titles missing from contracts.jsonl or not from test: {missing}")
    return titles, records


def main(argv: list[str]) -> None:
    titles, records = load_inputs()
    check_frozen()
    done = json.loads(OUT.read_text(encoding="utf-8"))["summary"]["run"]["finished_titles"] if OUT.exists() else []
    print(f"Eval: {len(titles)} contracts, {len(done)} finished. Frozen prompts: {FROZEN}. "
          f"Tokens today {llm.tokens_today():,} / {config.TOKENS_PER_DAY:,}.")
    if "--run" not in argv:
        print("Plan only; no API calls made. Use --run to start or resume.")
        return
    tee = Tee(sys.stdout, LOG)
    sys.stdout = tee
    try:
        run_eval(titles, records, OUT)
    finally:
        sys.stdout = tee.stream
        tee.close()


if __name__ == "__main__":
    main(sys.argv[1:])

"""Accuracy check: run the agents on the demo files and compare with the answer keys.

    python -m app.evaluate                       # invoices, resumes and calls
    python -m app.evaluate --only invoices       # one part (invoices, resumes, calls)
    python -m app.evaluate --limit 10            # the first N files of each part

It uses the real model (LLM_* settings) but its own scratch database and upload folder, built
fresh from the demo seed, so the app's data is never touched. The same code paths as the app are
used: the Invoice Processor and the matching rules, the Resume Parser and Screener, the Call
Analyzer. How each answer key is read is fixed below, before any result is seen.
"""

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.import_demo import DATA_DIR, read_rows

# --- how the answer keys are read (fixed before any run) ---------------------------------------

# Resume fit from the deterministic score (0-100: 70 from verified required skills, 30 from years).
# "strong" means every required skill evidenced and enough years, which is exactly 100.
WEAK_BELOW = 60
BORDERLINE_OK = {"medium", "strong"}
_STOPWORDS = """
a an and are as at be by call do for from in into is it of on or our send the their them to up we
with will your today tomorrow
"""
STOPWORDS = set(_STOPWORDS.split())


def expected_invoice(text: str) -> dict[str, Any]:
    """Answer-key wording → the outcome(s) that count as right, and whether code must flag
    instructions to the AI."""
    t = text.lower()
    injection = "prompt injection" in t
    if "credit note" in t or "quotation" in t:
        ok = {"not_an_invoice"}
    elif "reminder" in t or "past-due" in t:
        ok = {"not_an_invoice", "duplicate"}
    elif "duplicate" in t:
        ok = {"duplicate"}
    elif "ambiguous" in t:
        ok = {"no_po:ambiguous"}
    elif "missing po" in t:
        ok = {"no_po:missing"}
    elif "unknown po" in t:
        ok = {"no_po:not_found"}
    elif "vendor mismatch" in t:
        ok = {"mismatch:vendor"}
    elif "arithmetic" in t:
        ok = {"mismatch:line_items"}
    elif "mismatch" in t:
        ok = {"mismatch:amount"}
    elif "match" in t:
        ok = {"matched"}
    else:  # e.g. "prompt injection - must be flagged" alone: any outcome, as long as it's flagged
        ok = set()
    return {"ok": ok, "injection": injection, "payable": ok == {"matched"}}


def invoice_outcomes(result: Any) -> set[str]:
    """What the app decided, in the same vocabulary as `expected_invoice`."""
    kinds = {a.kind for a in result.anomalies}
    if kinds & {"duplicate", "number_conflict"}:
        return {"duplicate"}
    if "not_an_invoice" in kinds:
        return {"not_an_invoice"}
    if "unknown_vendor" in kinds:
        return {"unknown_vendor"}
    match = result.match
    if match is None:
        return {"not_saved"}
    if match.status == "matched":
        return {"matched"}
    if match.status == "no_po":
        no_po = [a for a in result.anomalies if a.kind == "no_po"]
        reason = no_po[0].detail.get("reason", "missing") if no_po else "missing"
        return {f"no_po:{reason}"}
    fields = {d.field for d in match.differences}
    out = set()
    if "vendor" in fields:
        out.add("mismatch:vendor")
    if "amount_minor" in fields:
        out.add("mismatch:amount")
    if fields & {"line_items_total", "line_math"}:
        out.add("mismatch:line_items")
    return out or {"mismatch:other"}


def score_resume(row: dict[str, str], got: dict[str, Any]) -> dict[str, Any]:
    """Compare one parsed and screened resume with its answer-key row. The app stores whole years
    and some keys use half years (0.5, 2.5), so years count as right within one year."""
    band = resume_band(got["score"])
    fit = row["expected_fit"]
    same = lambda a, b: (a or "").strip().lower() == (b or "").strip().lower()  # noqa: E731
    return {
        "score": got["score"],
        "band": band,
        "name_ok": same(got["name"], row["name"]),
        "email_ok": same(got["email"], row["email"]),
        "years_ok": got["years"] is not None
        and abs(got["years"] - float(row["years_experience"])) <= 1,
        "fit_ok": band in BORDERLINE_OK if fit == "borderline" else band == fit,
    }


def resume_band(score: int) -> str:
    if score >= 100:
        return "strong"
    return "weak" if score < WEAK_BELOW else "medium"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in STOPWORDS}


def action_item_recall(expected: str, found: list[str]) -> tuple[int, int]:
    """Approximate: an expected item counts as found when a model action item shares a content
    word with it. Items that say nothing should happen ("no deal exists") are not counted."""
    items = [i.strip() for i in expected.split(";") if i.strip()]
    items = [i for i in items if not re.search(r"must be ignored|no conversation|no deal", i)]
    found_words = [_words(f) for f in found]
    hits = sum(1 for item in items if any(_words(item) & w for w in found_words))
    return hits, len(items)


# --- the scratch world ------------------------------------------------------------------------


def _scratch(workdir: Path, data: Path) -> sessionmaker[Session]:
    """A new SQLite database and upload folder under `workdir`, holding what the app holds after
    the demo import: the seed, plus the sheet's vendors and jobs (invoices name those vendors,
    resumes apply to those jobs)."""
    os.environ["UPLOAD_DIR"] = str(workdir / "uploads")
    from app.config import get_settings

    get_settings.cache_clear()
    from app import import_demo
    from app.models import Base
    from app.seed import seed

    # SQLite allows one writer at a time, and an agent call keeps its log row open while the model
    # thinks; so parallel resumes queue for the lock (WAL lets readers carry on meanwhile).
    engine = create_engine(
        f"sqlite:///{workdir / 'evaluate.db'}",
        connect_args={"check_same_thread": False, "timeout": 900},
    )

    @event.listens_for(engine, "connect")
    def _wal(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed(db, secrets.token_urlsafe(16))
        report = import_demo.Report()
        vendors, jobs = read_rows("vendors.csv", data), read_rows("jobs.csv", data)
        import_demo.import_vendors(db, vendors, _user(db, "buyer"), report, False)
        import_demo.import_jobs(db, jobs, _user(db, "hr.recruiter"), report, False)
        db.commit()
    return factory


def _user(db: Session, handle: str) -> Any:
    from app.config import DEMO_DOMAIN
    from app.models import User

    return db.scalar(select(User).where(User.email == f"{handle}@{DEMO_DOMAIN}"))


# --- the three parts ----------------------------------------------------------------------------


def evaluate_invoices(
    factory: sessionmaker[Session],
    llm: Any,
    data: Path,
    limit: int | None,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    from app.agents.runner import TaskContext
    from app.models.enums import Department
    from app.services import finance
    from app.services.uploads import save_upload

    rows = read_rows("answer_keys/invoices.csv", data)[:limit]
    items = []
    with factory() as db:
        ctx = TaskContext(actor=_user(db, "finance.clerk"))
        for n, row in enumerate(rows, 1):  # in key order: duplicates depend on what came before
            expected = expected_invoice(row["expected_result"])
            try:
                upload = save_upload(
                    db,
                    filename=row["file"],
                    data=(data / "invoices" / row["file"]).read_bytes(),
                    department=Department.finance,
                    actor=ctx.actor,
                )
                result = finance.process_invoice_upload(db, llm, upload, ctx)
                db.commit()
                got, flagged, error = invoice_outcomes(result), bool(result.suspicious_text), None
            except Exception as exc:
                db.rollback()
                got, flagged, error = {"error"}, False, str(exc)[:200]
            right_outcome = not expected["ok"] or bool(got & expected["ok"])
            right = right_outcome and (flagged or not expected["injection"])
            items.append(
                {
                    "file": row["file"],
                    "expected": row["expected_result"],
                    "got": sorted(got),
                    "flagged": flagged,
                    "correct": right,
                    "error": error,
                    "paid_wrongly": "matched" in got
                    and not expected["payable"]
                    and bool(expected["ok"]),
                    "false_alarm": expected["payable"] and "matched" not in got,
                }
            )
            progress(f"  invoice {n}/{len(rows)} {row['file']}: {'ok' if right else 'WRONG'}")
    return {
        "total": len(items),
        "correct": sum(i["correct"] for i in items),
        "paid_wrongly": sum(i["paid_wrongly"] for i in items),
        "false_alarms": sum(i["false_alarm"] for i in items),
        "items": items,
    }


def _one_resume(
    factory: sessionmaker[Session], llm: Any, data: Path, row: dict[str, str]
) -> dict[str, Any]:
    from app.agents.runner import TaskContext
    from app.models import Job
    from app.models.enums import Department
    from app.services import hr
    from app.services.uploads import save_upload

    with factory() as db:
        ctx = TaskContext(actor=_user(db, "hr.recruiter"))
        upload = save_upload(
            db,
            filename=row["file"],
            data=(data / "resumes" / row["file"]).read_bytes(),
            department=Department.hr,
            actor=ctx.actor,
        )
        candidate = hr.add_candidate_from_resume(db, llm, upload, ctx)
        db.commit()
        job = db.scalar(select(Job).where(Job.title == row["intended_job"]))
        score = hr.screen_candidate(db, llm, job, candidate, ctx).score
        db.commit()
        return {
            "name": candidate.name,
            "email": candidate.email,
            "years": candidate.years_experience,
            "score": score,
        }


def evaluate_resumes(
    factory: sessionmaker[Session],
    llm: Any,
    data: Path,
    limit: int | None,
    workers: int,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    rows = read_rows("answer_keys/resumes.csv", data)[:limit]
    items = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_one_resume, factory, llm, data, row): row for row in rows}
        for n, future in enumerate(as_completed(futures), 1):
            row = futures[future]
            try:
                got, error = future.result(), None
            except Exception as exc:
                got, error = None, str(exc)[:200]
            item: dict[str, Any] = {
                "file": row["file"],
                "job": row["intended_job"],
                "expected_fit": row["expected_fit"],
                "error": error,
            }
            if got:
                try:
                    item |= score_resume(row, got)
                except (KeyError, TypeError, ValueError) as exc:  # a bad key row, not a crash
                    item["error"] = f"could not score: {exc}"
            items.append(item)
            progress(f"  resume {n}/{len(rows)} {row['file']}: {item.get('band', 'failed')}")
    done = [i for i in items if not i["error"]]
    by_fit: dict[str, list[int]] = defaultdict(list)
    for i in done:
        by_fit[i["expected_fit"]].append(i["score"])
    return {
        "total": len(items),
        "failed": len(items) - len(done),
        "name_ok": sum(i["name_ok"] for i in done),
        "email_ok": sum(i["email_ok"] for i in done),
        "years_ok": sum(i["years_ok"] for i in done),
        "fit_ok": sum(i["fit_ok"] for i in done),
        "mean_score_by_expected_fit": {k: round(sum(v) / len(v), 1) for k, v in by_fit.items()},
        "items": items,
    }


def evaluate_calls(
    factory: sessionmaker[Session],
    llm: Any,
    data: Path,
    limit: int | None,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    from app.docx_text import docx_text
    from app.models import Lead
    from app.services import calls

    rows = read_rows("answer_keys/transcripts.csv", data)[:limit]
    items = []
    with factory() as db:
        rep = _user(db, "sales.rep")
        for n, row in enumerate(rows, 1):
            text = docx_text((data / "transcripts" / row["file"]).read_bytes())
            lead = Lead(
                name="Caller",
                company=row["file"][:160],
                email="caller@example.com",
                owner_id=rep.id,
            )
            db.add(lead)
            db.commit()
            try:
                call = calls.add_call(
                    db,
                    llm,
                    rep,
                    file_name=f"{Path(row['file']).stem}.txt",
                    data=text.encode(),
                    lead_id=lead.id,
                    ticket_id=None,
                    title=None,
                )
                out = calls.to_out(db, call)
                analysis, error = out.analysis, out.analysis_error
            except Exception as exc:
                db.rollback()
                analysis, error, out = None, str(exc)[:200], None
            item: dict[str, Any] = {
                "file": row["file"],
                "scenario": row["scenario"],
                "expected_sentiment": row["expected_sentiment"],
                "error": error,
            }
            if analysis is not None:
                hits, wanted = action_item_recall(
                    row["expected_action_items"], [a.task for a in analysis.action_items]
                )
                item |= {
                    "sentiment": analysis.sentiment,
                    "sentiment_ok": analysis.sentiment == row["expected_sentiment"],
                    "action_hits": hits,
                    "action_expected": wanted,
                    "flagged": bool(out and out.suspicious_text),
                }
            items.append(item)
            progress(f"  call {n}/{len(rows)} {row['file']}: {item.get('sentiment', 'failed')}")
    done = [i for i in items if "sentiment" in i]
    injection = [i for i in done if i["scenario"] == "prompt_injection"]
    return {
        "total": len(items),
        "failed": len(items) - len(done),
        "sentiment_ok": sum(i["sentiment_ok"] for i in done),
        "action_items_found": sum(i["action_hits"] for i in done),
        "action_items_expected": sum(i["action_expected"] for i in done),
        "injection_flagged": f"{sum(i['flagged'] for i in injection)}/{len(injection)}",
        "items": items,
    }


# --- report -------------------------------------------------------------------------------------


def summary(results: dict[str, Any]) -> str:
    lines = []
    if inv := results.get("invoices"):
        lines.append(
            f"Invoices: {inv['correct']}/{inv['total']} handled as the answer key says; "
            f"{inv['paid_wrongly']} would have been paid wrongly; "
            f"{inv['false_alarms']} good invoices sent to review."
        )
    if res := results.get("resumes"):
        ok = res["total"] - res["failed"]
        lines.append(
            f"Resumes: {ok}/{res['total']} parsed; name {res['name_ok']}/{ok}, email "
            f"{res['email_ok']}/{ok}, years (±1) {res['years_ok']}/{ok}; fit band "
            f"{res['fit_ok']}/{ok}. Mean score by expected fit: "
            f"{res['mean_score_by_expected_fit']}."
        )
    if cal := results.get("calls"):
        ok = cal["total"] - cal["failed"]
        lines.append(
            f"Calls: {ok}/{cal['total']} analysed; sentiment {cal['sentiment_ok']}/{ok}; action "
            f"items found (approximate) {cal['action_items_found']}/"
            f"{cal['action_items_expected']}; "
            f"injection call flagged {cal['injection_flagged']}."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", default="invoices,resumes,calls")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--data", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--out", type=Path, default=Path(tempfile.gettempdir()) / "unify-evaluation.json"
    )
    args = parser.parse_args(argv)
    parts = {p.strip() for p in args.only.split(",")}

    from app.llm import get_llm

    llm = get_llm()
    say = lambda msg: print(msg, flush=True)  # noqa: E731
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="unify-eval-") as tmp:
        factory = _scratch(Path(tmp), args.data)
        results: dict[str, Any] = {"model": getattr(llm, "model", None)}
        if "invoices" in parts:
            say("invoices...")
            results["invoices"] = evaluate_invoices(factory, llm, args.data, args.limit, say)
        if "resumes" in parts:
            say("resumes...")
            results["resumes"] = evaluate_resumes(
                factory, llm, args.data, args.limit, args.workers, say
            )
        if "calls" in parts:
            say("calls...")
            results["calls"] = evaluate_calls(factory, llm, args.data, args.limit, say)
    results["minutes"] = round((time.monotonic() - started) / 60, 1)
    results["counts"] = dict(Counter(k for k in results if k in {"invoices", "resumes", "calls"}))
    args.out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print("\n" + summary(results))
    print(f"\nDetails: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

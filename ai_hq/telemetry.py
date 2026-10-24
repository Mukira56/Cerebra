"""Read-only, bounded orchestration telemetry; no inferred provider usage figures."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import defer
from .models import Task, Run, Event, Approval, Agent
from .security import redact


def seconds(start, end):
    try:
        first = datetime.fromisoformat(start)
        last = datetime.fromisoformat(end)
        first = first.replace(tzinfo=timezone.utc) if first.tzinfo is None else first
        last = last.replace(tzinfo=timezone.utc) if last.tzinfo is None else last
        return round(max(0, (last - first).total_seconds()), 2)
    except (TypeError, ValueError):
        return None


def snapshot(db, task_id=None):
    stamp = datetime.now(timezone.utc).isoformat()
    with db.Session() as session:
        query = select(Run).options(defer(Run.output), defer(Run.error)).order_by(Run.started_at.desc()).limit(500)
        if task_id:
            query = query.where(Run.task_id == task_id)
        runs = list(session.scalars(query))
        # Only fetch recent bounded log tails; do not reload hundreds of CLI transcripts every poll.
        details = {row.id: (row.output, row.error) for row in session.execute(
            select(Run.id, Run.output, Run.error).where(Run.id.in_([run.id for run in runs[:12]])))}
        task_query = select(Task).order_by(Task.updated_at.desc()).limit(200)
        if task_id:
            task_query = task_query.where(Task.id == task_id)
        tasks = {row.id: row for row in session.scalars(task_query)}
        missing = {run.task_id for run in runs} - tasks.keys()
        if missing:
            tasks.update({row.id: row for row in session.scalars(select(Task).where(Task.id.in_(missing)))})
        event_query = select(Event).order_by(Event.created_at.desc()).limit(60)
        approval_query = select(Approval).where(Approval.status == "PENDING").limit(200)
        if task_id:
            event_query = event_query.where(Event.task_id == task_id)
            approval_query = approval_query.where(Approval.task_id == task_id)
        events = [{"id": row.id, "task_id": row.task_id, "kind": row.kind,
                   "message": redact(row.message), "created_at": row.created_at}
                  for row in session.scalars(event_query)]
        approvals = [{"task_id": row.task_id, "kind": row.kind} for row in session.scalars(approval_query)]
        agents = [{"name": row.id, "available": row.status.get("available", False),
                   "execution_allowed": row.status.get("execution_allowed", False)}
                  for row in session.scalars(select(Agent))]
        records = []
        for run in runs:
            output, error = details.get(run.id, ("", ""))
            task = tasks.get(run.task_id)
            source = "live" if not run.simulated and task and task.mode == "live" else "mock"
            records.append({"id": run.id, "task_id": run.task_id, "agent": run.agent,
                "role": run.role, "status": run.status, "source": source,
                "started_at": run.started_at, "finished_at": run.finished_at,
                "duration_seconds": seconds(run.started_at, run.finished_at) if run.finished_at else None,
                "elapsed_seconds": seconds(run.started_at, stamp) if run.status == "running" else None,
                "output_tail": redact(output or "")[-1200:], "error": redact(error or "")[-600:]})
        task_records = [{"id": row.id, "description": redact(row.description), "state": row.state,
            "mode": row.mode, "assigned_agent": row.assigned_agent, "reviewer": row.reviewer,
            "retry_count": row.retry_count, "updated_at": row.updated_at,
            "tests_passed": sum(result.get("passed") is True for result in row.test_results),
            "test_commands": len(row.test_results)} for row in tasks.values()]
    metrics = {}
    for source in ("live", "mock"):
        metrics[source] = {}
        for provider in ("codex", "claude"):
            subset = [run for run in records if run["source"] == source and run["agent"] == provider]
            finished = [run for run in subset if run["status"] in {"succeeded", "failed", "interrupted"}]
            durations = [run["duration_seconds"] for run in finished if run["duration_seconds"] is not None]
            succeeded = sum(run["status"] == "succeeded" for run in finished)
            metrics[source][provider] = {"runs": len(subset), "completed": len(finished),
                "succeeded": succeeded, "failed": sum(run["status"] == "failed" for run in finished),
                "active": sum(run["status"] == "running" for run in subset),
                "success_percent": round(succeeded * 100 / len(finished), 1) if finished else None,
                "mean_duration_seconds": round(sum(durations) / len(durations), 2) if durations else None}
    return {"snapshot_at": stamp, "run_limit": 500, "runs": records, "tasks": task_records,
            "events": events, "approvals": approvals, "agents": agents, "metrics": metrics,
            "measurement_note": "Run duration includes CLI startup and orchestration. Tokens, cost, and model inference speed are not reported by this integration."}

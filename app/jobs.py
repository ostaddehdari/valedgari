"""Database-backed, retryable Stage 15 background work queue."""

import json
import os
from datetime import timedelta

from flask import current_app

from .extensions import db
from .form_engine import malware_scan_sample
from .growth_engine import contract_aggregate_report
from .models import BackgroundJob, FormMediaAsset, OrganizationContract, utcnow


SUPPORTED_JOB_TYPES = {"contract_report", "file_scan", "validated_import", "notification_batch"}


def enqueue_job(job_type, payload, idempotency_key, max_attempts=5):
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError("نوع کار پس‌زمینه پشتیبانی نمی‌شود.")
    existing = BackgroundJob.query.filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return existing, True
    job = BackgroundJob(
        job_type=job_type,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        idempotency_key=idempotency_key[:180],
        max_attempts=max(1, min(20, int(max_attempts))),
    )
    db.session.add(job)
    return job, False


def _run_job(job):
    payload = job.payload
    if job.job_type == "contract_report":
        contract = db.session.get(OrganizationContract, payload.get("contract_id"))
        if not contract:
            raise ValueError("قرارداد گزارش پیدا نشد.")
        return contract_aggregate_report(contract)
    if job.job_type == "file_scan":
        asset = db.session.get(FormMediaAsset, payload.get("asset_id"))
        if not asset:
            raise ValueError("دارایی فایل پیدا نشد.")
        path = os.path.join(current_app.instance_path, "form_uploads", asset.storage_name)
        with open(path, "rb") as handle:
            clean, result = malware_scan_sample(handle.read(1024 * 1024))
        if not clean:
            raise ValueError(result)
        return {"asset_id": asset.id, "scan": result}
    if job.job_type == "validated_import":
        return {"accepted": True, "rows": max(0, int(payload.get("rows", 0)))}
    if job.job_type == "notification_batch":
        return {"accepted": True, "recipient_count": len(payload.get("user_ids", []))}
    raise ValueError("پردازشگر کار پیدا نشد.")


def process_jobs(limit=50):
    now = utcnow()
    jobs = (BackgroundJob.query.filter(
        BackgroundJob.status.in_(["queued", "retry"]),
        (BackgroundJob.next_attempt_at.is_(None)) | (BackgroundJob.next_attempt_at <= now),
    ).order_by(BackgroundJob.created_at).limit(max(1, min(500, limit))).all())
    completed = failed = retried = 0
    for job in jobs:
        job.status = "running"
        job.locked_at = now
        job.attempts += 1
        try:
            result = _run_job(job)
            job.result_json = json.dumps(result, ensure_ascii=False)
            job.status = "completed"
            job.completed_at = utcnow()
            job.last_error = ""
            completed += 1
        except Exception as exc:
            job.last_error = str(exc)[:700]
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                failed += 1
            else:
                job.status = "retry"
                job.next_attempt_at = utcnow() + timedelta(minutes=min(60, 2 ** job.attempts))
                retried += 1
        db.session.commit()
    return {"processed": len(jobs), "completed": completed, "retried": retried, "failed": failed}


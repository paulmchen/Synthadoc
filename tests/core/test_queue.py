# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.core.queue import JobQueue, JobStatus


@pytest.mark.asyncio
async def test_enqueue_dequeue(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "paper.pdf"})
    job = await q.dequeue()
    assert job.id == job_id
    assert job.operation == "ingest"
    assert job.status == JobStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_complete_job(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    jobs = await q.list_jobs(status=JobStatus.COMPLETED)
    assert any(j.id == job_id for j in jobs)


@pytest.mark.asyncio
async def test_fail_retries_then_dies(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=2)
    await q.init()
    await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.fail(job.id, "timeout")
    job = await q.dequeue()
    await q.fail(job.id, "timeout")
    dead = await q.list_jobs(status=JobStatus.DEAD)
    assert len(dead) == 1


@pytest.mark.asyncio
async def test_delete_job_atomic(tmp_wiki):
    from synthadoc.storage.log import AuditDB
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    job_id = await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    await q.delete(job_id, audit_db=audit)
    all_jobs = await q.list_jobs()
    assert not any(j.id == job_id for j in all_jobs)


@pytest.mark.asyncio
async def test_queue_handles_overflow(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    for i in range(10):
        await q.enqueue("ingest", {"source": f"file{i}.pdf"})
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 10

import logging
import uuid
<<<<<<< HEAD
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import object_session

from app.models import ProcessingJob
from app.writer.client import writer_client
=======
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import object_session

from app.jobs_manager_run_service import recalculate_run_counts
from app.models import ProcessingJob
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e


class ProcessingStatusManager:
    """
    Manages processing job status, creation, updates, and cleanup.
<<<<<<< HEAD
    Handles all database operations related to job tracking via Writer Service.
    """

    def __init__(self, db_session: Any, logger: logging.Logger | None = None):
=======
    Handles all database operations related to job tracking.
    """

    def __init__(self, db_session: Any, logger: Optional[logging.Logger] = None):
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        self.db_session = db_session
        self.logger = logger or logging.getLogger(__name__)

    def generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return str(uuid.uuid4())

    def create_job(
        self,
        post_guid: str,
        job_id: str,
<<<<<<< HEAD
        run_id: str | None = None,
        *,
        requested_by_user_id: int | None = None,
        billing_user_id: int | None = None,
    ) -> ProcessingJob:
        """Create a new pending job record for the provided post."""
        job_data = {
            "id": job_id,
            "jobs_manager_run_id": run_id,
            "post_guid": post_guid,
            "status": "pending",
            "current_step": 0,
            "total_steps": 4,
            "progress_percentage": 0.0,
            "created_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "requested_by_user_id": requested_by_user_id,
            "billing_user_id": billing_user_id,
        }

        writer_client.action("create_job", {"job_data": job_data}, wait=True)

        self.db_session.expire_all()
        job = self.db_session.get(ProcessingJob, job_id)
        if not job:
            raise RuntimeError(f"Failed to create job {job_id}")
        return cast(ProcessingJob, job)

    def cancel_existing_jobs(self, post_guid: str, current_job_id: str) -> None:
        """Delete any existing active jobs for this post."""
        writer_client.action(
            "cancel_existing_jobs",
            {"post_guid": post_guid, "current_job_id": current_job_id},
            wait=True,
        )
        self.db_session.expire_all()
=======
        run_id: Optional[str] = None,
        triggered_by_user_id: Optional[int] = None,
        trigger_source: Optional[str] = None,
    ) -> ProcessingJob:
        """Create a new pending job record for the provided post."""
        # Create new job
        job = ProcessingJob(
            id=job_id,
            jobs_manager_run_id=run_id,
            post_guid=post_guid,
            triggered_by_user_id=triggered_by_user_id,
            trigger_source=trigger_source,
            status="pending",
            current_step=0,
            total_steps=4,
            progress_percentage=0.0,
            created_at=datetime.utcnow(),
        )
        self.db_session.add(job)
        if run_id:
            recalculate_run_counts(self.db_session)
        self.db_session.commit()
        return job

    def cancel_existing_jobs(self, post_guid: str, current_job_id: str) -> None:
        """Delete any existing active jobs for this post (called when we acquire the lock)."""
        existing_jobs = (
            ProcessingJob.query.filter_by(post_guid=post_guid)
            .filter(
                ProcessingJob.status.in_(["pending", "running"]),
                ProcessingJob.id != current_job_id,
            )
            .all()
        )

        for existing_job in existing_jobs:
            self.db_session.delete(existing_job)

        self.db_session.flush()
        recalculate_run_counts(self.db_session)
        self.db_session.commit()
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

    def update_job_status(
        self,
        job: ProcessingJob,
        status: str,
        step: int,
        step_name: str,
<<<<<<< HEAD
        progress: float | None = None,
    ) -> None:
        """Update job status in database."""
        # Cache job attributes before any operations that might expire the object
        job_id = job.id
        total_steps = job.total_steps
        is_bound = object_session(job) is not None

        self.logger.info(
            "[JOB_STATUS_UPDATE] job_id=%s status=%s step=%s step_name=%s bound=%s",
            job_id,
            status,
            step,
            step_name,
            is_bound,
        )

        if progress is None:
            progress = (step / total_steps) * 100.0

        writer_client.action(
            "update_job_status",
            {
                "job_id": job_id,
                "status": status,
                "step": step,
                "step_name": step_name,
                "progress": progress,
            },
            wait=True,
        )

        self.db_session.expire_all()

        if status in {"failed", "cancelled"}:
            self.logger.error(
                "[JOB_STATUS_ERROR] job_id=%s post_guid=%s status=%s step=%s step_name=%s progress=%.2f",
                job_id,
                job.post_guid,  # post_guid is safe - not cached but accessed before expire_all
                status,
                step,
                step_name,
                progress,
            )

    def mark_cancelled(self, job_id: str, error_message: str | None = None) -> None:
        writer_client.action(
            "mark_cancelled", {"job_id": job_id, "reason": error_message}, wait=True
        )
        self.db_session.expire_all()
        self.logger.info(f"Successfully cancelled job {job_id}")
=======
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update job status in database.

        For failed jobs, error_message should contain the error details.
        If error_message is not provided but status is 'failed', step_name
        will be used as the error message for backward compatibility.
        """
        self.logger.debug(
            ("update_job_status enter: job_id=%s status=%s step=%s bound=%s"),
            getattr(job, "id", None),
            status,
            step,
            object_session(job) is not None,
        )
        job.status = status
        job.current_step = step
        job.step_name = step_name

        # Set error_message for failed jobs
        if status == "failed":
            # Use explicit error_message if provided, otherwise fall back to step_name
            job.error_message = error_message if error_message else step_name
        elif status in ["completed", "skipped"]:
            # Clear error_message on success
            job.error_message = None

        if progress is not None:
            job.progress_percentage = progress
        else:
            # Calculate progress based on step
            job.progress_percentage = (step / job.total_steps) * 100.0

        if status == "running" and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in ["completed", "failed", "skipped", "cancelled"]:
            job.completed_at = datetime.utcnow()

        try:
            if job.jobs_manager_run_id:
                recalculate_run_counts(self.db_session)
            self.db_session.commit()
            if self.logger:
                self.logger.debug(
                    (
                        "update_job_status committed: job_id=%s status=%s step=%s progress=%.2f"
                    ),
                    getattr(job, "id", None),
                    job.status,
                    job.current_step,
                    job.progress_percentage,
                )
        except Exception as e:
            if self.logger:
                self.logger.error(
                    "update_job_status commit failed for job_id=%s: %s",
                    getattr(job, "id", None),
                    e,
                    exc_info=True,
                )
            raise

    def mark_cancelled(self, job_id: str, error_message: Optional[str] = None) -> None:
        # Use a fresh query to ensure we get the latest state
        job = self.db_session.query(ProcessingJob).filter_by(id=job_id).first()
        if not job:
            return

        job.status = "cancelled"
        job.error_message = error_message
        job.completed_at = datetime.utcnow()

        run_id = job.jobs_manager_run_id
        try:
            if run_id:
                recalculate_run_counts(self.db_session)
            self.db_session.commit()
            self.logger.info(f"Successfully cancelled job {job_id}")
        except Exception as e:
            self.logger.error(f"Failed to cancel job {job_id}: {e}")
            self.db_session.rollback()
            raise
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

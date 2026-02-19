from types import SimpleNamespace
from unittest import mock

from app.routes.jobs_routes import jobs_bp


def test_cancel_queued_jobs_returns_manager_result(app):
    app.testing = True
    app.register_blueprint(jobs_bp)
    client = app.test_client()

    expected = {
        "status": "success",
        "cancelled_job_ids": ["job-1", "job-2"],
        "message": "Cancelled 2 queued jobs",
    }

    with (
        mock.patch("app.routes.jobs_routes.get_jobs_manager") as mock_get_manager,
        mock.patch("app.routes.jobs_routes.db.session.expire_all") as mock_expire_all,
    ):
        mock_get_manager.return_value = SimpleNamespace(
            cancel_queued_jobs=mock.Mock(return_value=expected)
        )

        response = client.post("/api/jobs/cancel-queued")

    assert response.status_code == 200
    assert response.get_json() == expected
    mock_get_manager.return_value.cancel_queued_jobs.assert_called_once_with()
    mock_expire_all.assert_called_once_with()


def test_cancel_queued_jobs_returns_500_on_error(app):
    app.testing = True
    app.register_blueprint(jobs_bp)
    client = app.test_client()

    with (
        mock.patch("app.routes.jobs_routes.get_jobs_manager") as mock_get_manager,
        mock.patch("app.routes.jobs_routes.db.session.expire_all") as mock_expire_all,
    ):
        mock_get_manager.return_value = SimpleNamespace(
            cancel_queued_jobs=mock.Mock(side_effect=RuntimeError("boom"))
        )

        response = client.post("/api/jobs/cancel-queued")

    payload = response.get_json()
    assert response.status_code == 500
    assert payload["status"] == "error"
    assert payload["error_code"] == "CANCEL_QUEUED_FAILED"
    assert "boom" in payload["message"]
    mock_expire_all.assert_not_called()

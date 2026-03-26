from pathlib import Path

import pytest
from flask import Flask

from app.routes.main_routes import main_bp


@pytest.fixture
def app_with_static(tmp_path: Path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>podly shell</body></html>",
        encoding="utf-8",
    )

    app = Flask(__name__, static_folder=str(static_dir))
    app.testing = True
    app.register_blueprint(main_bp)

    yield app, static_dir


def test_extensionless_routes_fall_back_to_spa_shell(app_with_static):
    app, _ = app_with_static
    client = app.test_client()

    response = client.get("/podcasts")

    assert response.status_code == 200
    assert b"podly shell" in response.data


def test_missing_manifest_returns_404_instead_of_spa_shell(app_with_static):
    app, _ = app_with_static
    client = app.test_client()

    response = client.get("/manifest.json")

    assert response.status_code == 404


def test_missing_assetlinks_returns_404_instead_of_spa_shell(app_with_static):
    app, _ = app_with_static
    client = app.test_client()

    response = client.get("/.well-known/assetlinks.json")

    assert response.status_code == 404


def test_existing_assetlinks_file_is_served(app_with_static):
    app, static_dir = app_with_static
    assetlinks_dir = static_dir / ".well-known"
    assetlinks_dir.mkdir()
    assetlinks_path = assetlinks_dir / "assetlinks.json"
    assetlinks_path.write_text('[{"relation":[]}]', encoding="utf-8")

    client = app.test_client()
    response = client.get("/.well-known/assetlinks.json")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == [{"relation": []}]


def test_assetlinks_can_be_served_from_environment(app_with_static, monkeypatch):
    app, _ = app_with_static
    monkeypatch.setenv("PODLY_ANDROID_PACKAGE_NAME", "cloud.lukus.podly")
    monkeypatch.setenv(
        "PODLY_ANDROID_SHA256_CERT_FINGERPRINTS",
        "AA:BB:CC,DD:EE:FF",
    )

    client = app.test_client()
    response = client.get("/.well-known/assetlinks.json")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "cloud.lukus.podly",
                "sha256_cert_fingerprints": ["AA:BB:CC", "DD:EE:FF"],
            },
        }
    ]

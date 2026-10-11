import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("COURTSIDE_TOKEN", raising=False)
    with TestClient(create_app(tmp_path / "storage", embedded_worker=False, demo=False, auth_mode="local")) as client:
        yield client


@pytest.fixture
def video_file(tmp_path):
    path = tmp_path / "session.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (320, 240))
    for frame in range(90):
        image = np.full((240, 320, 3), (45, 80, 55), np.uint8)
        cv2.circle(image, (30 + frame * 2, 100), 4, (0, 230, 230), -1)
        writer.write(image)
    writer.release()
    return path


@pytest.fixture
def upload_options():
    return {
        "title": "Test practice",
        "player_name": "Test Player",
        "processing_consent": True,
        "age_group": "adult",
    }

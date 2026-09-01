import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.main as api_main


client = TestClient(api_main.app)


class StubModel:
    def predict(self, features):
        return np.array([3.0] * len(features))


@pytest.fixture(autouse=True)
def use_stub_model(monkeypatch) -> None:
    monkeypatch.setattr(
        api_main,
        "load_model_bundle",
        lambda: {"model": StubModel()},
    )


def test_predict_bug() -> None:
    response = client.get(
        "/predict",
        params={
            "description_length": 500,
            "issue_type": "Bug",
            "priority": "Major",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["predicted_duration_days"] >= 0
    assert body["predicted_duration_hours"] >= 0
    assert body["message"].startswith("Предсказанная длительность:")


def test_predict_story() -> None:
    response = client.get(
        "/predict",
        params={
            "description_length": 1500,
            "issue_type": "Story",
            "priority": "Minor",
        },
    )

    assert response.status_code == 200
    assert response.json()["predicted_duration_hours"] >= 0


def test_negative_description_length_is_rejected() -> None:
    response = client.get(
        "/predict",
        params={
            "description_length": -1,
            "issue_type": "Bug",
            "priority": "Major",
        },
    )

    assert response.status_code == 422

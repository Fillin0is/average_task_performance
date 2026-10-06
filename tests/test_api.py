import numpy as np
import pytest
from fastapi.testclient import TestClient

import api.main as api_main


client = TestClient(api_main.app)


class StubModel:
    def predict(self, features):
        assert list(features.columns) == [
            "Description_Issue_Length",
            "Description_Project_Length",
            "Initial_Type",
            "Initial_Priority",
        ]
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
            "description_issue_length": 500,
            "description_project_length": 146,
            "initial_type": "Bug",
            "initial_priority": "P3",
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
            "description_issue_length": 1500,
            "description_project_length": 320,
            "initial_type": "Story",
            "initial_priority": "P4",
        },
    )

    assert response.status_code == 200
    assert response.json()["predicted_duration_hours"] >= 0


def test_negative_issue_description_length_is_rejected() -> None:
    response = client.get(
        "/predict",
        params={
            "description_issue_length": -1,
            "description_project_length": 146,
            "initial_type": "Bug",
            "initial_priority": "P3",
        },
    )

    assert response.status_code == 422

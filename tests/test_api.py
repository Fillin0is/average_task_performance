import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api import service


client = TestClient(app)


class StubEmbedding:
    def encode(self, texts, **kwargs):
        assert texts == ["Issue description\nFirst comment\nSecond comment"]
        return np.zeros((1, 384))


class StubClassifier:
    def predict(self, features):
        assert list(features.columns) == service.FEATURE_COLUMNS
        assert features.loc[0, "Priority_At_Snapshot"] == "P3"
        assert features.loc[0, "Description_Over_100"] == 0
        return np.array([["1-7d"]])


class StubRegressor:
    def predict(self, features):
        return np.array([72.0])


@pytest.fixture
def request_data():
    return {
        "Project_ID": "1",
        "Priority_At_Snapshot": "Major",
        "Type_At_Snapshot": "Bug",
        "Creation_Day_Of_Week": 2,
        "Story_Point_At_Snapshot": None,
        "Has_Assignee_At_Snapshot": 1,
        "Description_At_Snapshot": "Issue description",
        "Comments_At_Snapshot": ["First comment", "Second comment"],
    }


def test_predict(monkeypatch, request_data):
    monkeypatch.setattr(service, "load_embedding_model", lambda: StubEmbedding())
    monkeypatch.setattr(service, "load_model", lambda name: StubClassifier() if name == "classifier" else StubRegressor())
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json() == {"predicted_class": "1-7d", "remaining_hours": 72.0, "remaining_days": 3.0}


def test_invalid_weekday(request_data):
    request_data["Creation_Day_Of_Week"] = 7
    assert client.post("/predict", json=request_data).status_code == 422


def test_missing_model(monkeypatch, request_data):
    monkeypatch.setattr(service, "load_embedding_model", lambda: StubEmbedding())
    def missing_model(name):
        raise FileNotFoundError("model unavailable")
    monkeypatch.setattr(service, "load_model", missing_model)
    assert client.post("/predict", json=request_data).status_code == 503

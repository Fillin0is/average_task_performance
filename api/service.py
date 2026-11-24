from functools import lru_cache

import joblib
import pandas as pd
from sentence_transformers import SentenceTransformer

from data_access.config import project_path
from data_access.snapshot_dataset import CLASS_LABELS, normalize_priority, normalize_type


MODEL_DIR = project_path.artifacts / "models" / "in_progress"
CATEGORICAL_FEATURES = ["Project_ID", "Priority_At_Snapshot", "Type_At_Snapshot"]
NUMERICAL_FEATURES = [
    "Creation_Day_Of_Week", "Description_Over_100",
    "Story_Point_At_Snapshot", "Has_Assignee_At_Snapshot",
]
EMBEDDING_FEATURES = [f"embedding_{i}" for i in range(384)]
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERICAL_FEATURES + EMBEDDING_FEATURES


@lru_cache(maxsize=5)
def load_model(name):
    path = MODEL_DIR / f"{name}.joblib"
    if not path.is_file():
        raise FileNotFoundError(f"Нет модели: {path}")
    model = joblib.load(path)
    if model.feature_names_ != FEATURE_COLUMNS:
        raise ValueError(f"Признаки модели не соответствуют API: {path}")
    return model


@lru_cache(maxsize=1)
def load_embedding_model():
    try:
        model = SentenceTransformer("BAAI/bge-small-en-v1.5", local_files_only=True)
    except OSError as error:
        raise FileNotFoundError("BGE model is not available in the local cache") from error
    model.max_seq_length = 512
    return model


def predict(request):
    # Как в ноутбуке: описание, затем комментарии в хронологическом порядке.
    text = (request.Description_At_Snapshot + "\n" + "\n".join(request.Comments_At_Snapshot)).strip()
    vector = load_embedding_model().encode([text], convert_to_numpy=True)[0]
    if len(vector) != len(EMBEDDING_FEATURES):
        raise ValueError("Размер эмбеддинга не соответствует обученной модели")

    values = {
        "Project_ID": request.Project_ID,
        "Priority_At_Snapshot": normalize_priority(pd.Series([request.Priority_At_Snapshot])).iloc[0],
        "Type_At_Snapshot": normalize_type(pd.Series([request.Type_At_Snapshot])).iloc[0],
        "Creation_Day_Of_Week": request.Creation_Day_Of_Week,
        "Description_Over_100": int(len(request.Description_At_Snapshot) > 100),
        "Story_Point_At_Snapshot": request.Story_Point_At_Snapshot,
        "Has_Assignee_At_Snapshot": request.Has_Assignee_At_Snapshot,
    }
    values.update(zip(EMBEDDING_FEATURES, vector))
    features = pd.DataFrame([values])[FEATURE_COLUMNS]
    # Числовые пропуски должны совпадать с представлением при обучении.
    features[NUMERICAL_FEATURES] = features[NUMERICAL_FEATURES].astype(float)
    classifier = load_model("classifier")
    predicted_class = str(classifier.predict(features).ravel()[0])
    if predicted_class not in CLASS_LABELS:
        raise ValueError(f"Неизвестный класс модели: {predicted_class}")

    regressor = load_model(predicted_class)
    hours = max(float(regressor.predict(features)[0]), 0.0)
    return {
        "predicted_class": predicted_class,
        "remaining_hours": round(hours, 2),
        "remaining_days": round(hours / 24, 2),
    }

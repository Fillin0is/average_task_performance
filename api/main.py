import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "artifacts" / "duration_model.joblib"

app = FastAPI(
    title="Issue Duration API",
    version="0.1.0",
    description="Baseline-прогноз календарной длительности закрытия задачи.",
)


class PredictionResponse(BaseModel):
    predicted_duration_days: float = Field(examples=[3.25])
    predicted_duration_hours: float = Field(examples=[78.0])
    message: str = Field(examples=["Предсказанная длительность: ~78.0 ч."])


@lru_cache(maxsize=1)
def load_model_bundle() -> dict:
    model_path = Path(os.getenv("DURATION_MODEL_PATH", DEFAULT_MODEL_PATH))
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}. Run: uv run python -m ml.train"
        )
    return joblib.load(model_path)


@app.get(
    "/predict",
    response_model=PredictionResponse,
    summary="Предсказать длительность задачи",
    description=(
        "Примеры для Swagger:\n\n"
        "1. `description_length=500`, `issue_type=Bug`, `priority=Major`\n"
        "2. `description_length=1500`, `issue_type=Story`, `priority=Minor`"
    ),
)
def predict_duration(
    description_length: Annotated[
        int,
        Query(ge=0, examples=[500], description="Количество символов в описании"),
    ],
    issue_type: Annotated[
        str,
        Query(min_length=1, examples=["Bug"], description="Исходный тип задачи"),
    ],
    priority: Annotated[
        str,
        Query(min_length=1, examples=["Major"], description="Исходный приоритет"),
    ],
) -> PredictionResponse:
    try:
        bundle = load_model_bundle()
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    features = pd.DataFrame(
        [
            {
                "Description_Length": description_length,
                "initial_type": issue_type.strip(),
                "initial_priority": priority.strip(),
            }
        ]
    )
    predicted_days = max(float(bundle["model"].predict(features)[0]), 0.0)
    predicted_hours = predicted_days * 24

    return PredictionResponse(
        predicted_duration_days=round(predicted_days, 2),
        predicted_duration_hours=round(predicted_hours, 1),
        message=f"Предсказанная длительность: ~{predicted_hours:.1f} ч.",
    )

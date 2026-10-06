import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from data_access.config import project_path


DEFAULT_MODEL_PATH = project_path.artifact("duration_model.joblib")


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
            f"Model not found at {model_path}. Save a compatible trained model first."
        )
    return joblib.load(model_path)


@app.get(
    "/predict", response_model=PredictionResponse,
    summary="Предсказать длительность задачи",
    description=(
        "Примеры для Swagger:\n\n"
        "1. `description_issue_length=500`, `description_project_length=146`, "
        "`initial_type=Bug`, `initial_priority=P3`\n"
        "2. `description_issue_length=1500`, `description_project_length=320`, "
        "`initial_type=Story`, `initial_priority=P4`"
    ),
)
def predict_duration(
    description_issue_length: Annotated[
        int,
        Query(ge=0, examples=[500], description="Количество символов в описании задачи"),
    ],
    description_project_length: Annotated[
        int,
        Query(ge=0, examples=[146], description="Количество символов в описании проекта"),
    ],
    initial_type: Annotated[
        str,
        Query(min_length=1, examples=["Bug"], description="Исходный тип задачи"),
    ],
    initial_priority: Annotated[
        Literal["P1", "P2", "P3", "P4", "P5", "Unassigned"],
        Query(examples=["P3"], description="Нормализованный исходный приоритет"),
    ],
) -> PredictionResponse:
    try:
        bundle = load_model_bundle()
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    features = pd.DataFrame(
        [
            {
                "Description_Issue_Length": description_issue_length,
                "Description_Project_Length": description_project_length,
                "Initial_Type": initial_type.strip(),
                "Initial_Priority": initial_priority,
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

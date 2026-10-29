from pydantic import BaseModel, Field


class PredictionResponse(BaseModel):
    predicted_duration_days: float = Field(examples=[3.25])
    predicted_duration_hours: float = Field(examples=[78.0])
    message: str = Field(examples=["Предсказанная длительность: ~78.0 ч."])

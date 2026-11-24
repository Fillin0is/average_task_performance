from pydantic import BaseModel, ConfigDict, Field


class PredictionRequest(BaseModel):
    """Данные задачи на момент перехода в работу."""

    model_config = ConfigDict(extra="forbid")

    Project_ID: str = Field(min_length=1, examples=["1"])
    Priority_At_Snapshot: str = Field(examples=["P3"])
    Type_At_Snapshot: str = Field(examples=["Bug"])
    Creation_Day_Of_Week: int = Field(ge=0, le=6, examples=[2])
    Story_Point_At_Snapshot: float | None = Field(ge=0, examples=[3])
    Has_Assignee_At_Snapshot: int | None = Field(ge=0, le=1, examples=[1])
    Description_At_Snapshot: str = Field(examples=["The application crashes when the user saves a task."])
    Comments_At_Snapshot: list[str] = Field(examples=[["The issue can be reproduced on Windows."]])


class PredictionResponse(BaseModel):
    predicted_class: str
    remaining_hours: float
    remaining_days: float

from fastapi import APIRouter, HTTPException

from api.schemas import PredictionRequest, PredictionResponse
from api.service import predict

router = APIRouter()


@router.post("/predict", response_model=PredictionResponse)
def predict_duration(request: PredictionRequest):
    try:
        return predict(request)
    except FileNotFoundError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

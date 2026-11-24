from fastapi import FastAPI

from api.router import router

app = FastAPI(title="Issue Duration API")
app.include_router(router)

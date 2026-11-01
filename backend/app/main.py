
from fastapi import FastAPI
from app.database import create_tables
from app.api.routes import router
from app.api.analytics import router as analytics_router


app = FastAPI(
    title="CartRecover",
    description="Abandoned Cart Recovery and Conversion Attribution System",
    version="1.0.0"
)

app.include_router(router)
app.include_router(analytics_router)


@app.on_event("startup")
def startup():
    create_tables()


@app.get("/")
def home():
    return {
        "application": "CartRecover",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}

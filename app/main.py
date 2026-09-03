from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ingestion
from app.scheduler import scheduler
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting background scheduler...")
    scheduler.start()
    yield
    print("Shutting down background scheduler...")
    scheduler.shutdown()

app = FastAPI(title="Socrates Research Engine Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://socrates-frontend.vercel.app",
        "https://socrates-frontend-blush.vercel.app",
        "https://socrates-frontend-amartya-sens-projects-b10cf8e1.vercel.app"
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion.router)

@app.get("/")
@app.head("/")
def read_root():
    return {"message": "Socrates Engine Live"}
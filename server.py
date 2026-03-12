from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
import web_api

load_dotenv()

app = FastAPI(title="Tobu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten this once the frontend domain is known
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---

class Comparison(BaseModel):
    other_date: str
    result: str  # "harder" | "easier" | "same"

class SubmitRatingsRequest(BaseModel):
    comparisons: list[Comparison]

class UpdateRatingRequest(BaseModel):
    result: str

class ChatRequest(BaseModel):
    message: str


# --- Routes ---

@app.get("/api/runs")
def get_runs(days: int = 90):
    return web_api.get_all_runs(days=days)


@app.get("/api/ratings/pending")
def get_pending(days: int = 30):
    return web_api.get_pending_ratings(days=days)


@app.get("/api/ratings/{date}")
def get_ratings(date: str):
    return web_api.get_run_ratings(date)


@app.post("/api/ratings/{date}")
def submit_ratings(date: str, body: SubmitRatingsRequest):
    try:
        web_api.submit_ratings(date, [c.model_dump() for c in body.comparisons])
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.patch("/api/ratings/{date}/{other_date}")
def update_rating(date: str, other_date: str, body: UpdateRatingRequest):
    try:
        web_api.update_rating(date, other_date, body.result)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/ratings/{date}")
def rerate_run(date: str, body: SubmitRatingsRequest):
    web_api.rerate_run(date, [c.model_dump() for c in body.comparisons])
    return {"status": "ok"}


@app.get("/api/elo")
def elo_leaderboard(days: int = 14):
    return web_api.get_elo_leaderboard(days=days)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/analysis/latest")
def get_latest_analysis():
    return web_api.get_latest_analysis()


@app.post("/api/analysis/generate")
def generate_analysis():
    try:
        return web_api.generate_analysis()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/analysis/{date}/chat")
def chat(date: str, body: ChatRequest):
    return web_api.send_chat_message(date, body.message)


@app.get("/api/summary/weekly")
def weekly_summary():
    return web_api.get_or_generate_weekly_summary()


from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

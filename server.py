from fastapi import FastAPI, HTTPException, Depends, Header
from garminconnect import GarminConnectConnectionError, GarminConnectTooManyRequestsError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
import web_api
from web_api import UserContext

load_dotenv()

app = FastAPI(title="Tobu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth ---

def get_user_context(
    x_garmin_email: Optional[str] = Header(None),
    x_garmin_password: Optional[str] = Header(None),
    x_anthropic_key: Optional[str] = Header(None),
) -> UserContext:
    if not x_garmin_email or not x_garmin_password or not x_anthropic_key:
        raise HTTPException(
            status_code=401,
            detail="Credentials required. Open Settings and enter your Garmin and Anthropic credentials.",
        )
    return UserContext(
        user_id=x_garmin_email,
        garmin_email=x_garmin_email,
        garmin_password=x_garmin_password,
        anthropic_key=x_anthropic_key,
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
def get_runs(days: int = 90, ctx: UserContext = Depends(get_user_context)):
    return web_api.get_all_runs(ctx, days=days)


@app.get("/api/ratings/pending")
def get_pending(days: int = 30, ctx: UserContext = Depends(get_user_context)):
    return web_api.get_pending_ratings(ctx, days=days)


@app.get("/api/ratings/{date}")
def get_ratings(date: str, ctx: UserContext = Depends(get_user_context)):
    return web_api.get_run_ratings(date, ctx)


@app.post("/api/ratings/{date}")
def submit_ratings(date: str, body: SubmitRatingsRequest, ctx: UserContext = Depends(get_user_context)):
    try:
        web_api.submit_ratings(date, [c.model_dump() for c in body.comparisons], ctx)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.patch("/api/ratings/{date}/{other_date}")
def update_rating(date: str, other_date: str, body: UpdateRatingRequest, ctx: UserContext = Depends(get_user_context)):
    try:
        web_api.update_rating(date, other_date, body.result, ctx)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/ratings/{date}")
def rerate_run(date: str, body: SubmitRatingsRequest, ctx: UserContext = Depends(get_user_context)):
    web_api.rerate_run(date, [c.model_dump() for c in body.comparisons], ctx)
    return {"status": "ok"}


@app.get("/api/elo")
def elo_leaderboard(days: int = 14, ctx: UserContext = Depends(get_user_context)):
    return web_api.get_elo_leaderboard(ctx, days=days)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/sync")
def sync_garmin(days: int = 30, ctx: UserContext = Depends(get_user_context)):
    try:
        return web_api.sync_from_garmin(ctx, days=days)
    except (GarminConnectTooManyRequestsError, GarminConnectConnectionError):
        raise HTTPException(status_code=429, detail="Garmin is rate-limiting login attempts. Please try again later.")


@app.get("/api/analysis/latest")
def get_latest_analysis(ctx: UserContext = Depends(get_user_context)):
    return web_api.get_latest_analysis(ctx)


@app.post("/api/analysis/generate")
def generate_analysis(ctx: UserContext = Depends(get_user_context)):
    try:
        return web_api.generate_analysis(ctx)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/analysis/{date}/chat")
def chat(date: str, body: ChatRequest, ctx: UserContext = Depends(get_user_context)):
    return web_api.send_chat_message(date, body.message, ctx)


@app.get("/api/summary/weekly")
def weekly_summary(ctx: UserContext = Depends(get_user_context)):
    return web_api.get_or_generate_weekly_summary(ctx)


from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

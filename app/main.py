from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import API_KEY
from app.database import close_db, init_db
from app.routers import bookings, reset, slots

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Clinic Booking API",
    version="1.0.0",
    description="Task 1 — Koya Cohort 4 Assessment Booking API (Levels 1–5)",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Error Handlers — ensuring every error strictly matches {"error": "<message>"}
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail)},
        headers=headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract the first human-readable validation error
    error_msg = "Invalid request payload"
    if exc.errors():
        first = exc.errors()[0]
        field = first.get("loc", ["field"])[-1]
        msg = first.get("msg", "Invalid value")
        error_msg = f"{field}: {msg}"
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": error_msg},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error"},
    )

# Public endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}

@app.get("/api/public-config", tags=["Config"])
async def public_config():
    return {"apiKey": API_KEY}

# Routers
app.include_router(reset.router)
app.include_router(slots.router)
app.include_router(bookings.router)

# Mount static files for the web application
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

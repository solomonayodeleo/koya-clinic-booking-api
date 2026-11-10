import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/clinic_booking")
API_KEY = os.getenv("API_KEY", "koya_sec_2026_demo")
PORT = int(os.getenv("PORT", "8000"))

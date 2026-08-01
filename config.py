"""
Configuration for Philadelphia Business Outreach scraper.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "outreach.db"

# 8-county Philadelphia metro (PA + South Jersey)
METRO_BBOX = {
    "west": -76.00,
    "east": -74.35,
    "south": 39.50,
    "north": 40.61,
}
METRO_COUNTIES = {
    "Philadelphia County",
    "Montgomery County",
    "Delaware County",
    "Bucks County",
    "Chester County",
    "Camden County",
    "Burlington County",
    "Gloucester County",
}

# License types that are not operating businesses
NON_BUSINESS_LICENSE_TYPES = {
    "Rental",
    "Dumpster License - Private Property",
    "Dumpster License - Public ROW",
    "Vacant Residential Property / Lot",
    "Vacant Commercial Property / Lot",
    "High Rise",
    "Handbill Distribution",
}

# Overture S3 settings
OVERTURE_S3_REGION = "us-west-2"
OVERTURE_STAC_URL = "https://stac.overturemaps.org/catalog.json"

# OpenDataPhilly CARTO API (no key needed)
CARTO_API = "https://phl.carto.com/api/v2/sql"

# Optional API keys for enrichment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")

# Scraping settings
REQUEST_TIMEOUT = 15
CRAWL_DELAY = 1.0  # seconds between website requests (be respectful)
MAX_PAGES_PER_SITE = 3  # home + contact + about
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Outreach eligibility
CALL_QUEUE_MIN_SCORE = 25.0
SENDABLE_VERIFY_STATUSES = ("valid", "role_ok", "deliverable")

# Email extraction regex
EMAIL_PATTERN = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"

# Junk email domains to filter out (not real business contacts)
JUNK_DOMAINS = {
    "example.com", "test.com", "email.com", "domain.com",
    "yoursite.com", "yourdomain.com", "company.com",
    "sentry.io", "wixpress.com", "squarespace.com",
    "wordpress.com", "googleapis.com", "cloudflare.com",
    "w3.org", "schema.org", "facebook.com", "twitter.com",
    "instagram.com", "linkedin.com", "google.com",
}

# CRM / API
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
DEMO_STATS = os.getenv("DEMO_STATS", "0") == "1"
DEFAULT_DEAL_VALUE = float(os.getenv("DEFAULT_DEAL_VALUE", "2500"))
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

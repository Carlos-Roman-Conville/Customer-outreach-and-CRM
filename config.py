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

# Tristate coverage: Pennsylvania, New Jersey, Delaware (full states)
TRISTATE_BBOX = {
    "west": -80.55,
    "east": -73.85,
    "south": 38.40,
    "north": 42.30,
}
TRISTATE_STATES = ("US-PA", "US-NJ", "US-DE")

# Backward-compatible aliases (legacy metro naming)
METRO_BBOX = TRISTATE_BBOX
METRO_COUNTIES: set[str] = set()

# License types that are not operating businesses
NON_BUSINESS_LICENSE_TYPES = {
    "Rental",
    "Dumpster License - Private Property",
    "Dumpster License - Public ROW",
    "Vacant Residential Property / Lot",
    "Vacant Commercial Property / Lot",
    "High Rise",
    "Handbill Distribution",
    "Hazardous Materials",
    "Vendor - Sidewalk Sales",
    "Public Garage / Parking Lot",
}

# --- License / registration enrichment ---
PA_DOS_API = "https://data.pa.gov/resource/xvd7-5r2c.json"
PA_DOS_CSV = "https://data.pa.gov/api/views/xvd7-5r2c/rows.csv?accessType=DOWNLOAD"
PA_EXCLUDED_REGISTRATION_TYPES = {
    "Domestic Nonprofit Corporation",
    "Foreign Nonprofit Corporation",
    "Domestic Credit Union",
    "Authority",
    "Domestic Land Bank",
    "Foreign Professional Association",
}

PHILLY_CAL_TABLE = "com_act_licenses"
PHILLY_BLI_TABLE = "business_licenses"

PA_SALES_TAX_API = "https://data.pa.gov/resource/ugeq-ckxd.json"
PA_SALES_TAX_CSV = (
    "https://data.pa.gov/api/views/ugeq-ckxd/rows.csv?accessType=DOWNLOAD"
)

NPPES_FILES_PAGE = "https://download.cms.gov/nppes/NPI_Files.html"
NPPES_TARGET_STATES = frozenset({"PA", "NJ", "DE"})

NJ_SEARCH_URL = "https://www.njportal.com/DOR/BusinessNameSearch/Search/BusinessName"
NJ_REQUEST_DELAY = 2.0  # seconds between portal requests

DE_LICENSE_API = "https://data.delaware.gov/resource/5zy2-grhr.json"
DE_LICENSE_CSV = "https://data.delaware.gov/api/views/5zy2-grhr/rows.csv?accessType=DOWNLOAD"

LICENSE_DATA_MAX_AGE_DAYS = 7

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
PLACES_REQUEST_DELAY = 0.1  # seconds between Google Places API calls
MAX_PAGES_PER_SITE = 3  # home + contact + about
SCAN_WORKERS = 12
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Outreach eligibility
CALL_QUEUE_MIN_SCORE = 44.0
SENDABLE_VERIFY_STATUSES = ("valid", "role_ok", "deliverable")

# ICP scoring (v4)
ICP_WEIGHTS = {
    "revenue_tier": {"A": 30, "B": 15, "C": 5, "U": 0},
    "has_license": 10,
    "has_email": 8,
    "multi_location_indie": 8,
    "independent": 4,
    "has_website": 2,
}
ICP_PENALTIES = {
    "chain_hard": -15,
    "chain_mid": -8,
    "solo_operator": -8,
}
ICP_SCORE_VERSION = 4
KNOWN_BOOKING_VENDORS = {
    "housecall_pro",
    "servicetitan",
    "jobber",
    "mindbody",
    "vagaro",
    "fresha",
    "nexhealth",
    "janeapp",
    "zocdoc",
    "toast",
    "opentable",
    "resy",
    "styleseat",
    "glossgenius",
    "booksy",
    "acuity",
    "calendly",
    "schedulicity",
    "setmore",
    "simplybook",
    "square_appointments",
}
SOLO_OPERATOR_CATEGORIES = (
    "real_estate_service/real_estate_agent",
    "financial_service/insurance_agency",
)
# ICP_IMPUTED_MEANS — populate from a stratified sample once a factor
# crosses ~20% checked coverage, then freeze. Do not recompute per run.

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

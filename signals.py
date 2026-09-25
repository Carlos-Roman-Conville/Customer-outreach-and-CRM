"""
Website signal scanner — detect tech stack, booking platforms, and extract site data.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
from tqdm import tqdm

from config import CALL_QUEUE_MIN_SCORE, CRAWL_DELAY, MAX_PAGES_PER_SITE, SCAN_WORKERS
from db import (
    DB_PATH,
    clear_business_signals,
    connect,
    init_db,
    record_signal,
    upsert_contact,
    utc_now,
)
from enrich import fetch_html

SCAN_PATHS = ["/contact", "/about"]

SIGNAL_PATTERNS: dict[str, dict[str, tuple[str, ...]]] = {
    "website_builder": {
        "wordpress": ("/wp-content/", "/wp-includes/", "wp-json"),
        "wix": ("static.wixstatic.com", "wixsite.com"),
        "squarespace": ("static1.squarespace.com", "sqsp.net", "<!-- This is Squarespace. -->"),
        "godaddy_builder": ("godaddysites.com", "img1.wsimg.com"),
        "weebly": ("weebly.com", "cdn2.editmysite.com"),
        "webflow": ("assets.website-files.com", "data-wf-site", "data-wf-page"),
        "duda": ("du-site.com", "multiscreensite.com"),
        "joomla": ("/media/jui/",),
        "drupal": ("Drupal.settings", "/sites/default/files/"),
        "hubspot_cms": ("hs-sites.com", "cos-cdn.hubspot"),
        "elementor": ("elementor/assets/", "data-elementor-type"),
        "divi": ("et_pb_", "/Divi/"),
        "shopify": ("cdn.shopify.com", "myshopify.com"),
    },
    "payment_pos": {
        "square": ("squarecdn.com", "js.squareup.com"),
        "stripe": ("js.stripe.com",),
        "paypal": ("paypal.com/sdk", "paypalobjects.com"),
        "clover": ("clover.com",),
        "toast_pos": ("toasttab.com",),
        "lightspeed": ("lightspeedhq.com",),
        "spoton": ("spoton.com",),
        "authorize_net": ("authorize.net",),
        "braintree": ("braintreegateway.com",),
    },
    "email_marketing": {
        "mailchimp": ("list-manage.com", "chimpstatic.com", "mc-validate.js"),
        "constant_contact": ("constantcontact.com", "ctctcdn.com"),
        "brevo": ("sendinblue.com", "brevo.com", "sibforms.com"),
        "klaviyo": ("static.klaviyo.com",),
        "activecampaign": ("trackcmp.net",),
        "convertkit": ("convertkit.com",),
        "mailerlite": ("assets.mailerlite.com",),
        "drip": ("getdrip.com",),
        "flodesk": ("flodesk.com",),
    },
    "crm": {
        "hubspot": ("js.hs-scripts.com", "hs-analytics.net"),
        "salesforce": ("force.com", "pardot.com"),
        "gohighlevel": ("msgsndr.com", "leadconnectorhq.com"),
        "keap": ("infusionsoft.com", "infusionsoft.app"),
        "zoho": ("salesiq.zoho.com", "zohowebstatic.com"),
        "pipedrive": ("pipedrivewebforms.com",),
    },
    "analytics": {
        "google_analytics": ("google-analytics.com", "gtag/js"),
        "google_tag_manager": ("googletagmanager.com/gtm.js",),
        "facebook_pixel": ("fbevents.js",),
        "microsoft_clarity": ("clarity.ms",),
        "hotjar": ("hotjar.com", "_hjSettings"),
        "tiktok_pixel": ("analytics.tiktok.com",),
        "linkedin_insight": ("snap.licdn.com",),
    },
    "social_media": {
        "facebook": ("facebook.com/pages/", "facebook.com/profile"),
        "linkedin": ("linkedin.com/company/",),
        "youtube": ("youtube.com/channel/", "youtube.com/@"),
        "tiktok": ("tiktok.com/@",),
        "yelp": ("yelp.com/biz/",),
        "nextdoor": ("nextdoor.com/",),
    },
    "reviews_reputation": {
        "birdeye": ("birdeye.com",),
        "trustpilot": ("widget.trustpilot.com",),
        "yotpo": ("staticw2.yotpo.com",),
        "nicejob": ("widget.nicejob.co",),
        "gatherup": ("gatherup.com",),
        "grade_us": ("grade.us",),
        "podium_reviews": ("connect.podium.com",),
        "google_reviews_embed": ("elfsight.com",),
    },
    "forms": {
        "jotform": ("jotform.com", "jotformcdn.com"),
        "typeform": ("typeform.com",),
        "gravity_forms": ("gform_wrapper", "gravityforms"),
        "wpforms": ("wpforms",),
        "contact_form_7": ("wpcf7", "contact-form-7"),
        "google_forms": ("docs.google.com/forms",),
        "ninja_forms": ("ninja-forms",),
        "hubspot_forms": ("hbspt.forms.create", "hsforms.com"),
    },
    "call_tracking": {
        "callrail": ("cdn.callrail.com",),
        "calltrackingmetrics": ("calltrackingmetrics.com",),
        "whatconverts": ("whatconverts.com",),
    },
    "booking": {
        "housecall_pro": ("housecallpro.com",),
        "servicetitan": ("servicetitan.com",),
        "jobber": ("getjobber.com",),
        "booksy": ("booksy.com",),
        "vagaro": ("vagaro.com",),
        "square_appointments": ("squareup.com/appointments", "book.squareup.com"),
        "acuity": ("acuityscheduling.com",),
        "calendly": ("calendly.com",),
        "mindbody": ("mindbodyonline.com", "mindbody.io"),
        "schedulicity": ("schedulicity.com",),
        "setmore": ("setmore.com",),
        "fresha": ("fresha.com",),
        "glossgenius": ("glossgenius.com",),
        "styleseat": ("styleseat.com",),
        "zocdoc": ("zocdoc.com",),
        "nexhealth": ("nexhealth.com",),
        "janeapp": ("janeapp.com", "jane.app"),
        "opentable": ("opentable.com",),
        "resy": ("resy.com",),
        "toast": ("toasttab.com",),
        "simplybook": ("simplybook.me",),
    },
    "chat": {
        "podium": ("podium.com",),
        "tawk": ("tawk.to", "embed.tawk.to"),
        "intercom": ("widget.intercom.io", "intercomSettings"),
        "drift": ("js.driftt.com",),
        "tidio": ("code.tidio.co",),
        "zendesk": ("zdassets.com", "zopim.com"),
        "livechat": ("livechatinc.com",),
        "freshchat": ("wchat.freshchat.com",),
        "olark": ("olark.com",),
        "crisp": ("client.crisp.chat",),
        "manychat": ("manychat.com",),
        "whatsapp": ("wa.me/", "api.whatsapp.com"),
    },
    "online_ordering": {
        "chownow": ("direct.chownow.com",),
        "doordash_storefront": ("direct.doordash.com",),
        "bentobox": ("getbento.com",),
        "popmenu": ("popmenu.com",),
        "www_olo": ("www.olo.com",),
        "gloriafood": ("gloriafood.com",),
        "slice": ("slicelife.com",),
    },
    "ecommerce": {
        "woocommerce": ("woocommerce", "/wp-content/plugins/woocommerce/"),
        "bigcommerce": ("cdn11.bigcommerce.com",),
        "ecwid": ("app.ecwid.com",),
        "square_online": ("square.site",),
    },
    "healthcare_dental": {
        "patientpop": ("patientpop.com",),
        "solutionreach": ("solutionreach.com",),
        "weave": ("getweave.com",),
        "demandforce": ("demandforce.com",),
        "revenuewell": ("revenuewell.com",),
        "localmed": ("localmed.com",),
    },
    "advertising": {
        "google_ads": ("googleads.g.doubleclick.net", "googleadservices.com"),
        "google_lsa": ("google.com/localservices",),
    },
    "field_service": {
        "fieldedge": ("fieldedge.com",),
        "servicefusion": ("servicefusion.com",),
        "kickserv": ("kickserv.com",),
        "mhelpdesk": ("mhelpdesk.com",),
        "service_autopilot": ("serviceautopilot.com",),
        "workiz": ("workiz.com",),
        "fieldpulse": ("fieldpulse.com",),
        "servicem8": ("servicem8.com",),
    },
    "sms_marketing": {
        "eztexting": ("eztexting.com",),
        "simpletexting": ("simpletexting.com",),
        "slicktext": ("slicktext.com",),
        "attentive": ("attn.tv",),
    },
    "loyalty": {
        "fivestars": ("fivestars.com",),
        "smile_io": ("smile.io",),
        "tapmango": ("tapmango.com",),
    },
    "lead_directories": {
        "angi": ("angi.com", "angieslist.com"),
        "homeadvisor": ("homeadvisor.com",),
        "thumbtack": ("thumbtack.com",),
        "bbb": ("bbb.org",),
        "houzz": ("houzz.com",),
    },
    "seo": {
        "yoast": ("<!-- This site is optimized with the Yoast", "yoast-schema"),
        "rankmath": ("rank-math",),
        "aioseo": ("aioseo",),
    },
    "accessibility": {
        "accessibe": ("acsbapp.com",),
        "userway": ("cdn.userway.org",),
    },
    "popups_conversion": {
        "optinmonster": ("optinmonster.com",),
        "privy": ("privy.com",),
        "justuno": ("justuno.com",),
    },
    "video_media": {
        "youtube_embed": ("youtube.com/embed",),
        "vimeo_embed": ("player.vimeo.com",),
        "wistia": ("fast.wistia.com",),
    },
    "hosting": {
        "wp_engine": ("wpenginepowered.com",),
        "siteground": ("sgoptimize",),
        "netlify": ("netlify.app",),
        "vercel": ("vercel.app",),
    },
    "menu_platform": {
        "singleplatform": ("singleplatform.com",),
        "musthavemenus": ("musthavemenus.com",),
        "menufy": ("menufy.com",),
    },
    "accounting": {
        "quickbooks": ("quickbooks.intuit.com",),
        "freshbooks": ("freshbooks.com",),
        "wave": ("waveapps.com",),
    },
}

GENERIC_SIGNALS: dict[str, tuple[str, ...]] = {
    "has_booking_cta": (
        "book now",
        "schedule now",
        "book online",
        "book appointment",
        "schedule appointment",
    ),
    "has_phone_on_site": (
        'href="tel:',
        "href='tel:",
    ),
    "is_hiring": (
        "we're hiring",
        "join our team",
        "now hiring",
    ),
    "offers_financing": (
        "financing available",
        "payment plans",
        "wisetack.com",
        "greensky.com",
        "synchrony.com",
    ),
}

BOOKING_LINK_RE = re.compile(
    r"\b(book(?:ing)?|appointment|schedule|reserve|reservation)\b",
    re.IGNORECASE,
)

SKIP_JSONLD_TYPES = {"person", "webpage", "website", "breadcrumblist"}

BUSINESS_JSONLD_TYPES = {
    "localbusiness",
    "organization",
    "restaurant",
    "dentist",
    "plumber",
    "electrician",
    "healthandbeautybusiness",
    "autorepair",
    "legalservice",
    "financialservice",
    "homeandconstructionbusiness",
    "store",
    "medicalclinic",
    "physician",
    "dentalclinic",
    "medicalbusiness",
    "autodealer",
    "autobodyshop",
    "barber",
    "beautysalon",
    "daycare",
    "drycleaningorlaundry",
    "employmentagency",
    "entertainmentbusiness",
    "exercisegym",
    "florist",
    "foodestablishment",
    "hairsalon",
    "healthclub",
    "hotel",
    "insuranceagency",
    "internetcafe",
    "lodgingbusiness",
    "nailsalon",
    "notary",
    "optician",
    "petstore",
    "professionalservice",
    "realestateagent",
    "recyclingcenter",
    "selfstorage",
    "shoppingcenter",
    "sportsactivitylocation",
    "travelagency",
    "veterinarycare",
}

IG_PROFILE_RE = re.compile(r'instagram\.com/([a-zA-Z0-9_.]+)/?(?:["\'\s>]|$)')
TW_PROFILE_RE = re.compile(r'(?:twitter|x)\.com/([a-zA-Z0-9_]+)/?(?:["\'\s>]|$)')


def _normalize_url(website: str) -> str:
    if not website.startswith("http"):
        return "https://" + website.lstrip("/")
    return website


def _scan_urls(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    urls = [base]
    for path in SCAN_PATHS:
        urls.append(base + path)
    return urls[:MAX_PAGES_PER_SITE]


def detect_social_profiles(html: str) -> list[dict[str, str]]:
    """Detect Instagram and Twitter/X business profile links (not share buttons)."""
    found: list[dict[str, str]] = []

    ig_exclude = {"p", "reel", "share", "embed", "explore", "accounts", "stories", ""}
    for match in IG_PROFILE_RE.finditer(html):
        handle = match.group(1).lower()
        if handle not in ig_exclude and len(handle) > 1:
            found.append({"kind": "social_media", "value": "instagram", "detail": handle})
            break

    tw_exclude = {
        "share",
        "intent",
        "hashtag",
        "i",
        "search",
        "home",
        "login",
        "compose",
        "messages",
        "settings",
        "",
    }
    for match in TW_PROFILE_RE.finditer(html):
        handle = match.group(1).lower()
        if handle not in tw_exclude and len(handle) > 1:
            found.append({"kind": "social_media", "value": "twitter_x", "detail": handle})
            break

    return found


def detect_signals(html: str) -> list[dict[str, str]]:
    lower = html.lower()
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for kind, vendors in SIGNAL_PATTERNS.items():
        for vendor, patterns in vendors.items():
            for pattern in patterns:
                if pattern.lower() in lower:
                    key = (kind, vendor)
                    if key not in seen:
                        seen.add(key)
                        found.append({"kind": kind, "value": vendor, "detail": pattern})
                    break

    for signal in detect_social_profiles(html):
        key = (signal["kind"], signal["value"])
        if key not in seen:
            seen.add(key)
            found.append(signal)

    for signal_name, patterns in GENERIC_SIGNALS.items():
        for pattern in patterns:
            if pattern.lower() in lower:
                key = ("generic", signal_name)
                if key not in seen:
                    seen.add(key)
                    found.append({"kind": "generic", "value": signal_name, "detail": pattern})
                break

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "")
        text = anchor.get_text(" ", strip=True)
        combined = f"{text} {href}".lower()
        if BOOKING_LINK_RE.search(combined):
            key = ("booking", "online_booking_link")
            if key not in seen:
                seen.add(key)
                detail = href[:200] if href else text[:200]
                found.append({"kind": "booking", "value": "online_booking_link", "detail": detail})
            break

    return found


def _jsonld_items(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            return [item for item in data["@graph"] if isinstance(item, dict)]
        return [data]
    return []


def _jsonld_type_str(item: dict) -> str:
    raw_type = item.get("@type", "")
    type_list = raw_type if isinstance(raw_type, list) else [raw_type]
    return " ".join(str(t) for t in type_list).lower()


def _is_skipped_jsonld(item: dict) -> bool:
    type_str = _jsonld_type_str(item)
    return any(skip in type_str for skip in SKIP_JSONLD_TYPES)


def _is_typed_business_jsonld(item: dict) -> bool:
    if _is_skipped_jsonld(item):
        return False
    type_str = _jsonld_type_str(item)
    return any(btype in type_str for btype in BUSINESS_JSONLD_TYPES)


def _has_useful_jsonld_fields(item: dict) -> bool:
    return any(
        item.get(field)
        for field in ("telephone", "address", "openingHours", "openingHoursSpecification")
    )


def _populate_structured_from_item(item: dict, result: dict) -> None:
    if not result["phone"]:
        phone = item.get("telephone")
        if phone:
            result["phone"] = str(phone).strip()

    if not result["address"]:
        addr = item.get("address", {})
        if isinstance(addr, dict):
            parts = [
                addr.get("streetAddress", ""),
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
                addr.get("postalCode", ""),
            ]
            full = ", ".join(p.strip() for p in parts if p and str(p).strip())
            if full:
                result["address"] = full

    if not result["hours"]:
        hours = item.get("openingHours") or item.get("openingHoursSpecification")
        if hours:
            result["hours"] = json.dumps(hours) if not isinstance(hours, str) else hours

    result["raw"] = json.dumps(item)


def extract_structured_data(html: str) -> dict:
    """Parse JSON-LD blocks for phone, address, hours."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {"phone": None, "address": None, "hours": None, "raw": None}
    fallback_item: dict | None = None

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        for item in _jsonld_items(data):
            if _is_typed_business_jsonld(item):
                _populate_structured_from_item(item, result)
                return result
            if fallback_item is None and _has_useful_jsonld_fields(item) and not _is_skipped_jsonld(item):
                fallback_item = item

    if fallback_item is not None:
        _populate_structured_from_item(fallback_item, result)

    return result


def extract_tel_phones(html: str) -> list[str]:
    """Extract US phone numbers from tel: href links."""
    phones: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("tel:"):
            raw = href.replace("tel:", "").replace("+1", "").strip()
            digits = re.sub(r"\D", "", raw)
            if len(digits) == 10:
                phones.add(digits)
    return list(phones)


def _dedupe_signals(signals: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for sig in signals:
        key = (sig["kind"], sig["value"])
        if key not in seen:
            seen.add(key)
            deduped.append(sig)
    return deduped


def _pick_booking_platform(signals: list[dict[str, str]]) -> str | None:
    booking_platform = None
    for sig in signals:
        if sig["kind"] != "booking":
            continue
        if sig["value"] == "online_booking_link":
            if booking_platform is None:
                booking_platform = sig["value"]
        else:
            return sig["value"]
    return booking_platform


def _scan_one_business(row) -> dict:
    gers_id = row["gers_id"]
    website = row["website"]
    stats = {"has_booking": False, "has_chat": False, "no_signal": False}

    try:
        base_url = _normalize_url(website)
        all_signals: list[dict[str, str]] = []
        html_chunks: list[str] = []
        pages_checked = 0

        for url in _scan_urls(base_url):
            if pages_checked >= MAX_PAGES_PER_SITE:
                break
            html = fetch_html(url)
            if html:
                all_signals.extend(detect_signals(html))
                html_chunks.append(html)
                pages_checked += 1
                if pages_checked < MAX_PAGES_PER_SITE:
                    time.sleep(CRAWL_DELAY)

        all_html = "\n".join(html_chunks)
        deduped = _dedupe_signals(all_signals)
        structured = extract_structured_data(all_html)
        tel_phones = extract_tel_phones(all_html)

        site_phone = structured["phone"]
        if not site_phone and tel_phones:
            site_phone = tel_phones[0]

        booking_platform = _pick_booking_platform(deduped)
        stats["has_booking"] = any(sig["kind"] == "booking" for sig in deduped)
        stats["has_chat"] = any(sig["kind"] == "chat" for sig in deduped)
        stats["no_signal"] = not deduped

        return {
            "gers_id": gers_id,
            "signals": deduped,
            "site_phone": site_phone,
            "all_phones": tel_phones,
            "site_address": structured["address"],
            "site_hours": structured["hours"],
            "site_structured_data": structured["raw"],
            "booking_platform": booking_platform,
            "stats": stats,
            "error": False,
        }
    except Exception:
        return {
            "gers_id": gers_id,
            "signals": [],
            "site_phone": None,
            "all_phones": [],
            "site_address": None,
            "site_hours": None,
            "site_structured_data": None,
            "booking_platform": None,
            "stats": stats,
            "error": True,
        }


def _upsert_phone_contact(conn, business_id: str, phone: str, source: str) -> None:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        return
    normalized = digits[-10:]
    existing = conn.execute(
        """
        SELECT 1 FROM contacts
        WHERE business_id = ?
          AND kind = 'phone'
          AND REPLACE(REPLACE(REPLACE(value, '-', ''), '(', ''), ')', '') LIKE ?
        """,
        (business_id, f"%{normalized}%"),
    ).fetchone()
    if not existing:
        upsert_contact(
            conn,
            {
                "business_id": business_id,
                "kind": "phone",
                "value": normalized,
                "source": f"site_{source}",
                "confidence": 0.7,
            },
        )


def _flush_results(results: list[dict], db_path=DB_PATH) -> None:
    now = utc_now()
    with connect(db_path) as conn:
        for result in results:
            gers_id = result["gers_id"]
            clear_business_signals(conn, gers_id)
            for sig in result.get("signals", []):
                record_signal(conn, gers_id, sig["kind"], sig["value"], sig.get("detail"))

            conn.execute(
                """
                UPDATE businesses
                SET site_phone = ?,
                    site_address = ?,
                    site_hours = ?,
                    site_structured_data = ?,
                    booking_platform = ?,
                    site_scanned_at = ?,
                    updated_at = ?
                WHERE gers_id = ?
                """,
                (
                    result.get("site_phone"),
                    result.get("site_address"),
                    result.get("site_hours"),
                    result.get("site_structured_data"),
                    result.get("booking_platform"),
                    now,
                    now,
                    gers_id,
                ),
            )

            if result.get("site_phone"):
                _upsert_phone_contact(conn, gers_id, result["site_phone"], "json_ld")
            for phone in result.get("all_phones", []):
                _upsert_phone_contact(conn, gers_id, phone, "tel_link")


def scan_business_sites(
    db_path=DB_PATH,
    limit: int | None = None,
    rescan_days: int = 90,
    queue_only: bool = False,
) -> dict[str, int]:
    init_db(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=rescan_days)).replace(microsecond=0).isoformat()

    query = """
        SELECT b.gers_id, b.website
        FROM businesses b
        JOIN targets t ON t.business_id = b.gers_id
        WHERE b.website IS NOT NULL AND TRIM(b.website) != ''
          AND (b.site_scanned_at IS NULL OR b.site_scanned_at < ?)
          AND t.revenue_tier != 'X'
    """
    params: list = [cutoff]

    if queue_only:
        query += """
          AND t.icp_score >= ?
          AND t.do_not_contact = 0
          AND EXISTS (
              SELECT 1 FROM contacts c
              WHERE c.business_id = b.gers_id AND c.kind = 'phone'
          )
        """
        params.append(CALL_QUEUE_MIN_SCORE)

    query += """
        ORDER BY t.revenue_tier ASC,
                 b.site_scanned_at IS NOT NULL ASC,
                 t.icp_score DESC
        LIMIT ?
    """
    params.append(limit if limit else 999_999)

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    stats = {"scanned": 0, "with_booking": 0, "with_chat": 0, "no_signal": 0, "errors": 0}
    pending: list[dict] = []

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        futures = {executor.submit(_scan_one_business, row): row for row in rows}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Scanning sites"):
            result = future.result()
            pending.append(result)

            row_stats = result.get("stats", {})
            stats["scanned"] += 1
            if result.get("error"):
                stats["errors"] += 1
            if row_stats.get("has_booking"):
                stats["with_booking"] += 1
            if row_stats.get("has_chat"):
                stats["with_chat"] += 1
            if row_stats.get("no_signal"):
                stats["no_signal"] += 1

            if len(pending) >= 50:
                _flush_results(pending, db_path)
                pending.clear()

    if pending:
        _flush_results(pending, db_path)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan business websites for tech stack signals")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rescan-days", type=int, default=90)
    parser.add_argument(
        "--queue-only",
        action="store_true",
        help="Only scan businesses currently in the call queue",
    )
    args = parser.parse_args()
    result = scan_business_sites(
        limit=args.limit,
        rescan_days=args.rescan_days,
        queue_only=args.queue_only,
    )
    print(result)

"""
Tiered email enrichment waterfall: crawl, domain guess, DuckDuckGo.
"""
from __future__ import annotations

import random
import re
import socket
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from tqdm import tqdm

from config import CRAWL_DELAY, EMAIL_PATTERN, JUNK_DOMAINS, REQUEST_TIMEOUT, USER_AGENT
from db import DB_PATH, connect, init_db, upsert_contact

CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

DIRECTORY_DOMAINS = {
    "yelp.com", "facebook.com", "instagram.com", "twitter.com",
    "linkedin.com", "yellowpages.com", "bbb.org", "tripadvisor.com",
    "google.com", "mapquest.com", "foursquare.com", "nextdoor.com",
}


class SearchRateLimited(Exception):
    """DuckDuckGo rate limit — should retry later, not treated as no website."""


def extract_emails_from_html(html: str) -> set[str]:
    emails: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip().lower()
            if re.match(EMAIL_PATTERN, email):
                emails.add(email)

    text = soup.get_text(separator=" ")
    for match in re.findall(EMAIL_PATTERN, text):
        emails.add(match.lower())
    for match in re.findall(EMAIL_PATTERN, html):
        emails.add(match.lower())

    return {
        e for e in emails
        if e.split("@")[1] not in JUNK_DOMAINS
        and not e.startswith("noreply")
        and not e.startswith("no-reply")
    }


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
            return resp.text
    except Exception:
        return None
    return None


def crawl_site_for_emails(base_url: str, max_pages: int = 3) -> set[str]:
    if not base_url:
        return set()
    if not base_url.startswith("http"):
        base_url = "https://" + base_url

    pages = [base_url] + [base_url.rstrip("/") + path for path in CONTACT_PATHS]
    emails: set[str] = set()
    checked = 0
    for url in pages:
        if checked >= max_pages:
            break
        html = fetch_html(url)
        if html:
            emails.update(extract_emails_from_html(html))
            checked += 1
    return emails


def slugify_name(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", name or "")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text.replace(" ", "")


def guess_domains(name: str, city: str | None) -> list[str]:
    slug = slugify_name(name)
    if not slug:
        return []
    city_slug = slugify_name(city or "philly")
    candidates = [
        f"{slug}.com",
        f"{slug}philly.com",
        f"{slug}philadelphia.com",
        f"{slug}{city_slug}.com",
    ]
    seen = set()
    out = []
    for domain in candidates:
        if domain not in seen:
            seen.add(domain)
            out.append(domain)
    return out


def domain_resolves(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False


def page_confirms_business(html: str, name: str, phone: str | None) -> bool:
    text = BeautifulSoup(html, "html.parser").get_text(" ").lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 3]
    if tokens and any(token in text for token in tokens[:3]):
        return True
    if phone:
        digits = re.sub(r"\D", "", phone)
        if digits and digits[-7:] in re.sub(r"\D", "", text):
            return True
    return False


def is_business_website(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return not any(domain.endswith(d) for d in DIRECTORY_DOMAINS)
    except Exception:
        return False


def search_business_website(name: str, address: str, city: str, zip_code: str) -> str | None:
    query = f"{name} {address} {city or 'Philadelphia'} PA {zip_code or ''}".strip()
    backoff = CRAWL_DELAY
    for attempt in range(4):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            for result in results:
                url = result.get("href", "")
                if is_business_website(url):
                    return url
            return None
        except Exception as exc:
            message = str(exc).lower()
            if "ratelimit" in message or "202" in message or "429" in message:
                if attempt == 3:
                    raise SearchRateLimited(str(exc)) from exc
                time.sleep(backoff + random.uniform(0, 1))
                backoff *= 2
                continue
            return None
    return None


def _businesses_needing_email(conn, limit: int | None = None):
    sql = """
        SELECT b.*
        FROM businesses b
        WHERE NOT EXISTS (
            SELECT 1 FROM contacts c
            WHERE c.business_id = b.gers_id AND c.kind = 'email'
        )
        ORDER BY b.confidence DESC NULLS LAST, b.name
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def enrich_emails(
    db_path=DB_PATH,
    limit: int | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    print("=" * 60)
    print("ENRICH: Email waterfall")
    print("=" * 60)

    init_db(db_path)
    stats = {
        "processed": 0,
        "emails_found": 0,
        "from_crawl": 0,
        "from_guess": 0,
        "from_ddg": 0,
        "rate_limited": 0,
    }

    with connect(db_path) as conn:
        rows = _businesses_needing_email(conn, limit=limit)
        print(f"  Businesses without email: {len(rows):,}")

        for row in tqdm(rows, desc="Enriching"):
            stats["processed"] += 1
            business_id = row["gers_id"]
            website = row["website"]
            phone_row = conn.execute(
                """
                SELECT value FROM contacts
                WHERE business_id = ? AND kind = 'phone'
                ORDER BY id LIMIT 1
                """,
                (business_id,),
            ).fetchone()
            phone = phone_row["value"] if phone_row else None

            found: set[str] = set()
            source = None

            if website:
                found = crawl_site_for_emails(website)
                if found:
                    source = "crawl"

            if not found:
                for domain in guess_domains(row["name"], row["city"]):
                    if not domain_resolves(domain):
                        continue
                    url = f"https://{domain}"
                    html = fetch_html(url)
                    if not html or not page_confirms_business(html, row["name"], phone):
                        continue
                    found = extract_emails_from_html(html)
                    if found:
                        upsert_contact(conn, {
                            "business_id": business_id,
                            "kind": "website",
                            "value": url,
                            "source": "guess",
                            "confidence": 0.4,
                        })
                        conn.execute(
                            "UPDATE businesses SET website = COALESCE(website, ?) WHERE gers_id = ?",
                            (url, business_id),
                        )
                        source = "guess"
                        break
                    time.sleep(CRAWL_DELAY)

            if not found:
                try:
                    discovered = search_business_website(
                        row["name"], row["address"] or "", row["city"] or "", row["zip"] or ""
                    )
                    if discovered:
                        upsert_contact(conn, {
                            "business_id": business_id,
                            "kind": "website",
                            "value": discovered,
                            "source": "ddg",
                            "confidence": 0.35,
                        })
                        conn.execute(
                            "UPDATE businesses SET website = COALESCE(website, ?) WHERE gers_id = ?",
                            (discovered, business_id),
                        )
                        found = crawl_site_for_emails(discovered)
                        if found:
                            source = "ddg"
                except SearchRateLimited:
                    stats["rate_limited"] += 1
                    print("\n  DuckDuckGo rate limited — stopping early. Re-run later to continue.")
                    break

            for email in found:
                upsert_contact(conn, {
                    "business_id": business_id,
                    "kind": "email",
                    "value": email,
                    "source": source or "crawl",
                    "confidence": 0.7 if source == "crawl" else 0.5,
                })

            if found:
                stats["emails_found"] += 1
                if source == "crawl":
                    stats["from_crawl"] += 1
                elif source == "guess":
                    stats["from_guess"] += 1
                elif source == "ddg":
                    stats["from_ddg"] += 1

            if stats["processed"] % batch_size == 0:
                time.sleep(CRAWL_DELAY)
            else:
                time.sleep(CRAWL_DELAY * 0.5)

    print(f"\n  Processed: {stats['processed']:,}")
    print(f"  Emails found: {stats['emails_found']:,}")
    print(f"    crawl: {stats['from_crawl']:,}")
    print(f"    guess: {stats['from_guess']:,}")
    print(f"    ddg: {stats['from_ddg']:,}")
    if stats["rate_limited"]:
        print(f"  Rate-limited runs: {stats['rate_limited']:,}")
    return stats


if __name__ == "__main__":
    enrich_emails()

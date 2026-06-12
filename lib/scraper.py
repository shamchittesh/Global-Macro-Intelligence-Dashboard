"""Edward Jones market report scraper.

Fetches and parses daily and weekly market reports from Edward Jones websites.
Includes caching integration with TTL-based freshness.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from lib.cache import read_cache, write_cache

logger = logging.getLogger(__name__)

# URLs
DAILY_RECAP_URL = (
    "https://www.edwardjones.ca/ca-en/market-news-insights/"
    "stock-market-news/daily-market-recap"
)
WEEKLY_UPDATE_URL = (
    "https://www.edwardjones.com/us-en/market-news-insights/"
    "stock-market-news/stock-market-weekly-update"
)

# Cache TTLs (hours)
DAILY_CACHE_TTL_HOURS = 4.0
WEEKLY_CACHE_TTL_HOURS = 12.0

# Request timeout (seconds)
REQUEST_TIMEOUT = 15

# Max body length
MAX_BODY_LENGTH = 5000


@dataclass
class MarketReport:
    """A scraped market report."""

    title: str
    publication_date: str
    body: str  # Max 5000 chars
    fetched_at: datetime
    available: bool = True
    error_message: str | None = None


def truncate_body(text: str) -> str:
    """Truncate report body to MAX_BODY_LENGTH characters.

    Args:
        text: Raw body text.

    Returns:
        Truncated text, at most MAX_BODY_LENGTH characters.
    """
    if len(text) <= MAX_BODY_LENGTH:
        return text
    return text[:MAX_BODY_LENGTH]


def _html_to_markdown(element) -> str:
    """Convert an HTML element to readable markdown, preserving structure.

    Converts headings, paragraphs, bold, italic, lists, and line breaks
    to markdown equivalents for rendering in Streamlit.
    """
    if element is None:
        return ""

    parts = []
    for child in element.children:
        if hasattr(child, "name") and child.name:
            tag = child.name.lower()
            text = child.get_text(strip=True)
            if not text and tag not in ("br", "hr"):
                continue

            if tag in ("h1", "h2"):
                parts.append(f"\n## {text}\n")
            elif tag == "h3":
                parts.append(f"\n### {text}\n")
            elif tag in ("h4", "h5", "h6"):
                parts.append(f"\n**{text}**\n")
            elif tag == "p":
                # Preserve inline formatting within paragraphs
                inner = _inline_to_markdown(child)
                if inner.strip():
                    parts.append(f"\n{inner}\n")
            elif tag in ("ul", "ol"):
                for li in child.find_all("li", recursive=False):
                    li_text = li.get_text(strip=True)
                    if li_text:
                        parts.append(f"- {li_text}")
                parts.append("")
            elif tag == "blockquote":
                # Handle multi-paragraph blockquotes
                bq_parts = []
                for bq_child in child.children:
                    if hasattr(bq_child, "name") and bq_child.name == "p":
                        bq_parts.append(f"> {bq_child.get_text(strip=True)}")
                    elif hasattr(bq_child, "name") and bq_child.name:
                        bq_parts.append(f"> {bq_child.get_text(strip=True)}")
                    else:
                        t = str(bq_child).strip()
                        if t:
                            bq_parts.append(f"> {t}")
                if bq_parts:
                    parts.append("\n" + "\n>\n".join(bq_parts) + "\n")
                else:
                    parts.append(f"\n> {text}\n")
            elif tag in ("br", "hr"):
                parts.append("\n---\n")
            elif tag in ("strong", "b"):
                parts.append(f"**{text}**")
            elif tag in ("em", "i"):
                parts.append(f"*{text}*")
            elif tag == "div":
                # Recurse into divs
                inner = _html_to_markdown(child)
                if inner.strip():
                    parts.append(inner)
            else:
                # Other tags: just get text
                if text:
                    parts.append(text)
        else:
            # Text node
            text = str(child).strip()
            if text:
                parts.append(text)

    return "\n".join(parts)


def _inline_to_markdown(element) -> str:
    """Convert inline HTML elements (within a paragraph) to markdown."""
    parts = []
    for child in element.children:
        if hasattr(child, "name") and child.name:
            tag = child.name.lower()
            text = child.get_text(strip=True)
            if tag in ("strong", "b"):
                parts.append(f"**{text}**")
            elif tag in ("em", "i"):
                parts.append(f"*{text}*")
            elif tag == "a":
                parts.append(text)
            elif tag == "br":
                parts.append("\n")
            else:
                parts.append(text)
        else:
            parts.append(str(child))
    return "".join(parts)
def _parse_edward_jones_page(html: str) -> tuple[str, str, str]:
    """Parse an Edward Jones market report page.

    Extracts title, publication date, and body as formatted markdown.

    Args:
        html: Raw HTML content.

    Returns:
        (title, publication_date, body_markdown) tuple.

    Raises:
        ValueError: If required content cannot be extracted.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try to find the article title
    title_elem = soup.find("h1")
    title = title_elem.get_text(strip=True) if title_elem else "Market Report"

    # Try to find publication date
    date_elem = soup.find("time")
    if date_elem:
        pub_date = date_elem.get_text(strip=True)
    else:
        date_meta = soup.find("meta", {"property": "article:published_time"})
        if date_meta and date_meta.get("content"):
            pub_date = date_meta["content"][:10]
        else:
            pub_date = "Date unavailable"

    # Extract body with formatting preserved as markdown
    # Try multiple content selectors in order of specificity
    content_elem = None

    # 1. Look for rich-text div (Edward Jones uses this)
    content_elem = soup.find("div", class_="rich-text")

    # 2. Try article tag
    if not content_elem:
        content_elem = soup.find("article")

    # 3. Try main content area but look for the content-heavy div inside
    if not content_elem:
        main = soup.find("main")
        if main:
            # Find the div with the most paragraph content
            divs = main.find_all("div", recursive=True)
            best_div = None
            best_p_count = 0
            for div in divs:
                p_count = len(div.find_all("p", recursive=False))
                if p_count > best_p_count:
                    best_p_count = p_count
                    best_div = div
            content_elem = best_div if best_div else main

    if content_elem:
        # Remove the title from body if it's duplicated
        if title_elem and content_elem.find("h1"):
            h1 = content_elem.find("h1")
            if h1:
                h1.decompose()
        body = _html_to_markdown(content_elem)
    else:
        # Last resort: convert paragraphs to markdown
        paragraphs = soup.find_all("p")
        body = "\n\n".join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )

    if not body.strip():
        raise ValueError("Could not extract report body from page")

    return title, pub_date, truncate_body(body)


def _fetch_report(url: str) -> MarketReport:
    """Fetch and parse a market report from a URL.

    Args:
        url: The report URL.

    Returns:
        MarketReport with parsed content or error state.
    """
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        response.raise_for_status()
    except requests.Timeout:
        return MarketReport(
            title="",
            publication_date="",
            body="",
            fetched_at=datetime.now(),
            available=False,
            error_message="Request timed out (>15 seconds)",
        )
    except requests.RequestException as e:
        return MarketReport(
            title="",
            publication_date="",
            body="",
            fetched_at=datetime.now(),
            available=False,
            error_message=f"Failed to fetch report: {e}",
        )

    try:
        title, pub_date, body = _parse_edward_jones_page(response.text)
    except (ValueError, Exception) as e:
        return MarketReport(
            title="",
            publication_date="",
            body="",
            fetched_at=datetime.now(),
            available=False,
            error_message=f"Failed to parse report: {e}",
        )

    return MarketReport(
        title=title,
        publication_date=pub_date,
        body=body,
        fetched_at=datetime.now(),
        available=True,
    )


def _report_from_cache(data: dict) -> MarketReport:
    """Reconstruct a MarketReport from cached dict data."""
    return MarketReport(
        title=data.get("title", ""),
        publication_date=data.get("publication_date", ""),
        body=data.get("body", ""),
        fetched_at=datetime.fromisoformat(data["fetched_at"]),
        available=data.get("available", True),
        error_message=data.get("error_message"),
    )


def _report_to_dict(report: MarketReport) -> dict:
    """Convert a MarketReport to a dict for caching."""
    return {
        "title": report.title,
        "publication_date": report.publication_date,
        "body": report.body,
        "fetched_at": report.fetched_at.isoformat(),
        "available": report.available,
        "error_message": report.error_message,
    }


def fetch_daily_recap() -> MarketReport:
    """Fetch Edward Jones daily market recap with caching.

    Checks cache first (4-hour TTL). On cache miss, fetches fresh.
    On fetch failure, serves stale cache if available.

    Returns:
        MarketReport with content or error state.
    """
    cache_key = "daily_report"

    # Check cache
    cached = read_cache(cache_key, max_age_hours=DAILY_CACHE_TTL_HOURS)
    if cached is not None:
        return _report_from_cache(cached)

    # Fetch fresh
    report = _fetch_report(DAILY_RECAP_URL)

    if report.available:
        write_cache(cache_key, _report_to_dict(report))
    else:
        # Try to serve stale cache on failure
        stale = read_cache(cache_key, max_age_hours=None)  # No TTL check
        if stale is not None:
            stale_report = _report_from_cache(stale)
            stale_report.error_message = (
                f"Fresh fetch failed. Showing cached report from "
                f"{stale_report.fetched_at.strftime('%Y-%m-%d %H:%M')}"
            )
            return stale_report

    return report


def fetch_weekly_update() -> MarketReport:
    """Fetch Edward Jones weekly market update with caching.

    Checks cache first (12-hour TTL). On cache miss, fetches fresh.
    On fetch failure, serves stale cache if available.

    Returns:
        MarketReport with content or error state.
    """
    cache_key = "weekly_report"

    # Check cache
    cached = read_cache(cache_key, max_age_hours=WEEKLY_CACHE_TTL_HOURS)
    if cached is not None:
        return _report_from_cache(cached)

    # Fetch fresh
    report = _fetch_report(WEEKLY_UPDATE_URL)

    if report.available:
        write_cache(cache_key, _report_to_dict(report))
    else:
        # Try to serve stale cache on failure
        stale = read_cache(cache_key, max_age_hours=None)  # No TTL check
        if stale is not None:
            stale_report = _report_from_cache(stale)
            stale_report.error_message = (
                f"Fresh fetch failed. Showing cached report from "
                f"{stale_report.fetched_at.strftime('%Y-%m-%d %H:%M')}"
            )
            return stale_report

    return report

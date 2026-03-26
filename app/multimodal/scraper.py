import re
import logging
from urllib.parse import urlparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from newspaper import Article

import nltk
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    import logging
    logging.getLogger(__name__).info("Downloading required NLTK data for Newspaper3k...")
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

from app.config import settings

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": settings.USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = settings.REQUEST_TIMEOUT


import ipaddress

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
            
        hostname = parsed.hostname
        if not hostname:
            return False
            
        if hostname.lower() in ("localhost", "local", "169.254.169.254", "127.0.0.1", "0.0.0.0"):
            return False
            
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass
            
        return True
    except Exception:
        return False


def get_domain(url: str) -> str:
    """Extract the domain name from a URL."""
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "unknown"


def scrape_with_newspaper(url: str) -> dict:
    """Primary scraper using Newspaper3k."""
    article = Article(url)
    article.headers = HEADERS

    article.download()
    article.parse()
    article.nlp()

    title   = article.title or ""
    text    = article.text or ""
    authors = article.authors or []
    date    = article.publish_date
    summary = article.summary or ""
    keywords = article.keywords or []

    date_str = date.strftime("%Y-%m-%d") if date else "Unknown"

    return {
        "title":    title.strip(),
        "text":     text.strip(),
        "author":   ", ".join(authors) if authors else "Unknown",
        "date":     date_str,
        "summary":  summary.strip(),
        "keywords": keywords,
        "method":   "newspaper3k"
    }


def scrape_with_beautifulsoup(url: str) -> dict:
    """Fallback scraper using BeautifulSoup."""
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    title = ""
    if soup.title:
        title = soup.title.string or ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else ""

    summary = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        summary = meta.get("content", "")

    author = "Unknown"
    for attr in [{"name": "author"}, {"property": "article:author"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            author = tag.get("content")
            break

    date_str = "Unknown"
    for attr in [
        {"property": "article:published_time"},
        {"name": "publishdate"},
        {"name": "date"},
    ]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            raw_date = tag.get("content", "")
            date_str = raw_date[:10]
            break

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    paragraphs = soup.find_all("p")
    body_text  = "\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40)

    return {
        "title":    title.strip(),
        "text":     body_text.strip(),
        "author":   author,
        "date":     date_str,
        "summary":  summary.strip(),
        "keywords": [],
        "method":   "beautifulsoup"
    }


def clean_text(text: str) -> str:
    """Post processing: remove excessive whitespace, ads, etc."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [l for l in lines if len(l) > 20 or l == ""]
    return "\n".join(lines).strip()


def extract_text_from_url(url: str) -> dict:
    """
    Main entry point -- scrapes a news article from a URL.
    Returns:
        dict with keys:
          - title (str)       : article headline
          - text (str)        : full article body text
          - author (str)      : author name(s)
          - date (str)        : publish date (YYYY-MM-DD)
          - summary (str)     : auto-generated summary
          - keywords (list)   : key topics
          - domain (str)      : source domain e.g. 'bbc.com'
          - method (str)      : scraping method used
          - char_count (int)  : length of extracted text
          - success (bool)    : whether extraction succeeded
          - error (str|None)  : error message if failed
    """
    if not is_valid_url(url):
        return {
            "title": "", "text": "", "author": "", "date": "",
            "summary": "", "keywords": [], "domain": "",
            "method": "none", "char_count": 0,
            "success": False, "error": f"Invalid URL: {url}"
        }

    domain = get_domain(url)
    result = None
    errors = []

    try:
        logger.info("Scraping with Newspaper3k: %s", url)
        result = scrape_with_newspaper(url)

        if len(result.get("text", "")) < 200:
            logger.warning("Newspaper3k returned short text -- trying BeautifulSoup")
            result = None
            errors.append("Newspaper3k: extracted too little text")

    except Exception as e:
        errors.append(f"Newspaper3k: {e}")
        logger.warning("Newspaper3k failed: %s", e)

    if result is None:
        try:
            logger.info("Scraping with BeautifulSoup: %s", url)
            result = scrape_with_beautifulsoup(url)
        except Exception as e:
            errors.append(f"BeautifulSoup: {e}")
            logger.error("BeautifulSoup also failed: %s", e)

    if result is None or not result.get("text"):
        return {
            "title": "", "text": "", "author": "", "date": "",
            "summary": "", "keywords": [], "domain": domain,
            "method": "none", "char_count": 0,
            "success": False,
            "error": " | ".join(errors) or "Both scrapers returned empty text"
        }

    result["text"]      = clean_text(result["text"])
    result["domain"]    = domain
    result["char_count"] = len(result["text"])
    result["success"]   = True
    result["error"]     = None

    logger.info(
        "Scraped '%s...' from %s (%d chars, method=%s)",
        result['title'][:60], domain, result['char_count'], result['method']
    )

    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        logger.info("Usage: python scraper.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    logger.info("Scraping: %s", url)
    logger.info("-" * 60)

    result = extract_text_from_url(url)

    if result["success"]:
        logger.info("Title    : %s", result['title'])
        logger.info("Author   : %s", result['author'])
        logger.info("Date     : %s", result['date'])
        logger.info("Source   : %s", result['domain'])
        logger.info("Method   : %s", result['method'])
        logger.info("Length   : %d characters", result['char_count'])
        logger.info("Summary  : %s", result['summary'][:300])
        logger.info("First 500 chars of body: %s", result['text'][:500])
    else:
        logger.info("Failed: %s", result['error'])
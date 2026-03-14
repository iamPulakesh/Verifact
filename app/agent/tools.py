import json
import logging
import os
from typing import Optional

from langchain.tools import tool
from langchain_groq import ChatGroq
from tavily import TavilyClient

from app.multimodal.ocr import extract_text_from_image
from app.multimodal.scraper import extract_text_from_url
from app.rag.retriever import retrieve_relevant_factchecks, format_retrieved_context
from app.agent.prompts import CLAIM_EXTRACTION_PROMPT, SOURCE_CREDIBILITY_PROMPT

logger = logging.getLogger(__name__)


def _get_llm():
    from app.config import settings
    return ChatGroq(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=1024,
        api_key=settings.GROQ_API_KEY,
    )


@tool
def ocr_tool(image_path: str) -> str:
    """
    Extracts all text from a news image file using OCR.
    Use this when the input is an image file path (.jpg, .png, etc.)
    Returns the extracted text as a string.
    """
    logger.info("[TOOL] ocr_tool called: %s", image_path)
    result = extract_text_from_image(image_path)

    if not result["success"]:
        return f"OCR_ERROR: {result['error']}"

    return (
        f"OCR_SUCCESS\n"
        f"Method: {result['method']}\n"
        f"Characters extracted: {result['char_count']}\n"
        f"--- EXTRACTED TEXT ---\n"
        f"{result['text']}"
    )


@tool
def url_scraper_tool(url: str) -> str:
    """
    Fetches and extracts the full text of a news article from a URL.
    Use this when the input is a web URL (http:// or https://).
    Returns the article title, author, date, and body text.
    """
    logger.info("[TOOL] url_scraper_tool called: %s", url)
    result = extract_text_from_url(url)

    if not result["success"]:
        return f"SCRAPE_ERROR: {result['error']}"

    return (
        f"SCRAPE_SUCCESS\n"
        f"Title  : {result['title']}\n"
        f"Author : {result['author']}\n"
        f"Date   : {result['date']}\n"
        f"Source : {result['domain']}\n"
        f"--- ARTICLE TEXT ---\n"
        f"{result['text'][:3000]}"
    )


@tool
def claim_extractor_tool(article_text: str) -> str:
    """
    Extracts the key falsifiable claims from a news article text.
    Use this after getting the article text (from OCR or scraper).
    Returns a JSON list of claim strings.
    """
    logger.info("[TOOL] claim_extractor_tool called")

    llm    = _get_llm()
    prompt = CLAIM_EXTRACTION_PROMPT.format(article_text=article_text[:3000])

    try:
        response = llm.invoke(prompt)
        raw      = response.content.strip()

        raw = raw.replace("```json", "").replace("```", "").strip()

        claims = json.loads(raw)
        if not isinstance(claims, list):
            claims = [str(claims)]

        logger.info("Extracted %d claims", len(claims))
        return json.dumps(claims)

    except json.JSONDecodeError:
        logger.warning("Could not parse claims as JSON -- returning raw")
        return json.dumps([raw[:500]])
    except Exception as e:
        logger.error("Claim extraction failed: %s", e)
        return json.dumps([f"Could not extract claims: {e}"])


@tool
def rag_search_tool(query: str) -> str:
    """
    Searches the local fact-check database (ChromaDB) for evidence
    related to a claim or topic.
    Use this to find existing fact-checks from PolitiFact, Snopes, etc.
    Returns formatted fact-check evidence with verdicts and sources.
    """
    logger.info("[TOOL] rag_search_tool called: %s", query[:60])

    try:
        docs      = retrieve_relevant_factchecks(query, top_k=4, use_mmr=True)
        formatted = format_retrieved_context(docs)

        if not docs:
            return "RAG_EMPTY: No relevant fact-checks found in database for this query."

        return f"RAG_RESULTS ({len(docs)} fact-checks found):\n{formatted}"

    except FileNotFoundError:
        return (
            "RAG_ERROR: Pinecone index not initialized. "
            "Run: python scripts/ingest_data.py"
        )
    except Exception as e:
        # Sanitize error message to prevent leaking API keys
        from app.config import settings
        err_msg = str(e)
        for secret in [
            settings.PINECONE_API_KEY, settings.GROQ_API_KEY,
            settings.TAVILY_API_KEY, settings.HF_TOKEN,
        ]:
            if secret:
                err_msg = err_msg.replace(secret, "***")
        logger.error("RAG search failed: %s", err_msg)
        return f"RAG_ERROR: {err_msg}"


@tool
def web_search_tool(query: str) -> str:
    """
    Searches the live web for current information to verify or debunk claims.
    Use this to find recent news, official statements, and cross-references.
    Returns top web search results with titles, URLs, and content snippets.
    """
    logger.info("[TOOL] web_search_tool called: %s", query[:60])

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key or tavily_key == "your_tavily_api_key_here":
        return "WEB_SEARCH_UNAVAILABLE: TAVILY_API_KEY not configured in .env"

    try:
        client  = TavilyClient(api_key=tavily_key)
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=4,
            include_answer=True,
        )

        output_parts = []

        if results.get("answer"):
            output_parts.append(f"DIRECT ANSWER: {results['answer']}\n")

        for i, result in enumerate(results.get("results", []), 1):
            title   = result.get("title", "No title")
            url     = result.get("url", "")
            content = result.get("content", "")[:400]
            score   = result.get("score", 0)

            output_parts.append(
                f"[Web Result #{i}] Score: {score:.2f}\n"
                f"Title  : {title}\n"
                f"URL    : {url}\n"
                f"Snippet: {content}"
            )

        return "WEB_RESULTS:\n" + "\n\n".join(output_parts)

    except Exception as e:
        logger.error("Web search failed: %s", e)
        return f"WEB_SEARCH_ERROR: {e}"


KNOWN_CREDIBILITY = {
    "bbc.com": 0.95,       "bbc.co.uk": 0.95,
    "reuters.com": 0.95,   "apnews.com": 0.95,
    "npr.org": 0.90,       "theguardian.com": 0.88,
    "nytimes.com": 0.87,   "washingtonpost.com": 0.87,
    "economist.com": 0.88, "nature.com": 0.95,
    "who.int": 0.97,       "cdc.gov": 0.97,
    "nasa.gov": 0.97,      "nih.gov": 0.97,
    "snopes.com": 0.92,    "politifact.com": 0.92,
    "factcheck.org": 0.92, "fullfact.org": 0.90,
    "apfactcheck.org": 0.93,
    "foxnews.com": 0.60,   "msnbc.com": 0.62,
    "huffpost.com": 0.65,  "buzzfeed.com": 0.60,
    "dailymail.co.uk": 0.50,
    "infowars.com": 0.05,  "naturalnews.com": 0.05,
    "beforeitsnews.com": 0.05,  "cnn.com": 0.85,
    "thehindu.com": 0.80,  "ndtv.com": 0.75,
    "timesofindia.com": 0.85,  "rt.com": 0.35,
    "tass.com": 0.40,  "sputniknews.com": 0.30,
    "xinhuanet.com": 0.40,  "globaltimes.cn": 0.35,
    "chinadaily.com.cn": 0.40,
}

@tool
def source_checker_tool(domain: str) -> str:
    """
    Checks the credibility of a news source domain.
    Use this to assess how trustworthy the article's source is.
    Returns a credibility score between 0.0 (unreliable) and 1.0 (highly reliable).
    """
    logger.info("[TOOL] source_checker_tool called: %s", domain)

    domain = domain.lower().strip().replace("www.", "")

    if domain in KNOWN_CREDIBILITY:
        score = KNOWN_CREDIBILITY[domain]
        tier  = "High" if score >= 0.80 else "Medium" if score >= 0.50 else "Low"
        return (
            f"SOURCE_CREDIBILITY\n"
            f"Domain     : {domain}\n"
            f"Score      : {score:.2f} / 1.00\n"
            f"Tier       : {tier}\n"
            f"Assessment : Known {'reputable' if score >= 0.80 else 'mixed' if score >= 0.50 else 'unreliable'} source"
        )

    try:
        llm    = _get_llm()
        prompt = SOURCE_CREDIBILITY_PROMPT.format(source_name=domain, url=domain)
        resp   = llm.invoke(prompt)
        raw    = resp.content.strip().replace("```json", "").replace("```", "")
        data   = json.loads(raw)
        score  = float(data.get("credibility_score", 0.5))
        reason = data.get("reason", "Unknown source")
        tier   = "High" if score >= 0.80 else "Medium" if score >= 0.50 else "Low"

        return (
            f"SOURCE_CREDIBILITY\n"
            f"Domain     : {domain}\n"
            f"Score      : {score:.2f} / 1.00\n"
            f"Tier       : {tier}\n"
            f"Assessment : {reason}"
        )
    except Exception as e:
        return (
            f"SOURCE_CREDIBILITY\n"
            f"Domain     : {domain}\n"
            f"Score      : 0.50 / 1.00\n"
            f"Tier       : Unknown\n"
            f"Assessment : Could not assess ({e})"
        )


ALL_TOOLS = [
    ocr_tool,
    url_scraper_tool,
    claim_extractor_tool,
    rag_search_tool,
    web_search_tool,
    source_checker_tool,
]
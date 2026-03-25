import sys
import logging
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agent.graph import get_agent, AgentState
from app.models.verdict import FactCheckVerdict, VerdictLabel

logger = logging.getLogger(__name__)


def run_fact_check(
    raw_input:   str,
    verbose:     bool = False,
) -> FactCheckVerdict:
    """
    Main entry point -- runs the full fact-checking agent pipeline.

    Args:
        raw_input : Image file path OR news article URL
        verbose   : If True, logs each agent step to console

    Returns: FactCheckVerdict- structured verdict with confidence + reasoning
    """
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    logger.info("Starting fact-check for: %s", raw_input[:80])
    start = time.time()

    initial_state: AgentState = {
        "raw_input":      raw_input,
        "input_type":     "",
        "article_text":   "",
        "article_title":  "",
        "article_source": "",
        "claims":         [],
        "rag_context":    "",
        "web_context":    "",
        "source_score":   0.5,
        "cot_reasoning":  "",
        "verdict_raw":    "",
        "verdict":        None,
        "messages":       [],
        "errors":         [],
    }

    try:
        agent        = get_agent()
        final_state  = agent.invoke(initial_state)
        elapsed      = time.time() - start

        verdict: FactCheckVerdict = final_state.get("verdict")

        if verdict is None:
            logger.error("Agent returned no verdict -- returning fallback")
            return _error_verdict(raw_input, "Agent returned no verdict", elapsed)

        logger.info(
            "Fact-check complete in %.1fs -- Verdict: %s (%.0f%%)",
            elapsed, verdict.verdict, verdict.confidence_score * 100
        )
        return verdict

    except Exception as e:
        elapsed = time.time() - start
        logger.error("Agent pipeline failed: %s", e)
        return _error_verdict(raw_input, str(e), elapsed)


def _error_verdict(raw_input: str, error: str, elapsed: float) -> FactCheckVerdict:
    """Returns a safe fallback verdict when the agent crashes."""
    return FactCheckVerdict(
        verdict           = VerdictLabel.UNVERIFIED,
        confidence_score  = 0.0,
        claims_analyzed   = [],
        reasoning_summary = f"Fact-checking failed: {error}",
        sources_consulted = ["None"],
        cot_steps         = f"Pipeline error after {elapsed:.1f}s: {error}",
        input_type        = "unknown",
        article_title     = "",
    )
import json, logging, re
from typing import TypedDict, Annotated, Optional
import operator

from langchain_groq import ChatGroq
try:
    from langchain_sambanova import ChatSambaNova
except ImportError:
    ChatSambaNova = None
try:
    from langchain_cerebras import ChatCerebras
except ImportError:
    ChatCerebras = None
    
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from app.agent.prompts import (
    FACT_CHECK_COT_PROMPT, SEARCH_QUERY_PROMPT, VERDICT_REPAIR_PROMPT,
)
from app.agent.tools import (
    rag_search_tool, web_search_tool, source_checker_tool,
)
from app.models.verdict import FactCheckVerdict, VerdictLabel, ClaimAnalysis
from app.multimodal.router import process_input
from app.config import settings
from app.agent.prompts import CLAIM_EXTRACTION_PROMPT


logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    raw_input:      str
    input_type:     str
    article_text:   str
    article_title:  str
    article_source: str
    claims:         list
    rag_context:    str
    web_context:    str
    source_score:   float
    cot_reasoning:  str
    verdict_raw:    str
    verdict:        Optional[object]
    messages:       Annotated[list, operator.add]
    errors:         list


def _get_llm():
    provider = getattr(settings, "LLM_PROVIDER", "groq")
    
    if provider == "sambanova" and ChatSambaNova:
        return ChatSambaNova(
            model=settings.SAMBANOVA_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            sambanova_api_key=settings.SAMBANOVA_API_KEY,
        )

    if provider == "cerebras" and ChatCerebras:
        return ChatCerebras(
            model=settings.CEREBRAS_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
            api_key=settings.CEREBRAS_API_KEY,
        )

    return ChatGroq(
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
        api_key=settings.GROQ_API_KEY,
    )


def input_router_node(state: AgentState) -> AgentState:
    logger.info("[NODE] input_router_node")
    
    result = process_input(state["raw_input"])

    if not result["success"]:
        error = f"Input processing failed: {result['error']}"
        return {**state, "input_type": result["input_type"], "article_text": "",
                "article_title": "Unknown", "article_source": state["raw_input"],
                "errors": state.get("errors", []) + [error],
                "messages": [HumanMessage(content=error)]}

    return {**state,
            "input_type": result["input_type"],
            "article_text": result["text"],
            "article_title": result["title"] or "Untitled Article",
            "article_source": result["source"],
            "messages": [HumanMessage(content=f"Loaded: {result['title'][:60]}")]}


def claim_extractor_node(state: AgentState) -> AgentState:
    logger.info("[NODE] claim_extractor_node")
    article_text = state.get("article_text", "")
    if not article_text:
        return {**state, "claims": ["No article text available"],
                "messages": [HumanMessage(content="No text to extract claims from.")]}

    
    llm = _get_llm()
    prompt = CLAIM_EXTRACTION_PROMPT.format(article_text=article_text[:3000])
    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if json_match:
            raw = json_match.group(1).strip()
        else:
            # Fallback for when there are no code blocks
            json_match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", raw)
            if json_match:
                raw = json_match.group(1).strip()
        
        claims = json.loads(raw)
        if not isinstance(claims, list):
            claims = [str(claims)]
        claims = [c.strip() for c in claims if c.strip()][:6]
    except Exception as e:
        logger.warning("Claim extraction fallback: %s", e)
        sentences = article_text.replace("\n"," ").split(". ")
        claims = [s.strip()+"." for s in sentences[:2] if len(s)>30]

    return {**state, "claims": claims,
            "messages": [HumanMessage(content=f"Extracted {len(claims)} claims.")]}


def evidence_retriever_node(state: AgentState) -> AgentState:
    logger.info("[NODE] evidence_retriever_node")
    claims = state.get("claims", [])
    article_title = state.get("article_title","")
    article_source = state.get("article_source","")

    rag_parts = []
    for claim in claims[:4]:
        result = rag_search_tool.invoke({"query": claim})
        rag_parts.append(f"Query: '{claim[:80]}'\n{result}")
    rag_context = "\n\n".join(rag_parts) if rag_parts else "No RAG results."

    llm = _get_llm()
    try:
        q_prompt = SEARCH_QUERY_PROMPT.format(
            claims=json.dumps(claims[:3]), article_title=article_title)
        q_resp = llm.invoke(q_prompt)
        q_raw  = q_resp.content.strip().replace("```json","").replace("```","")
        search_queries = json.loads(q_raw)
        if not isinstance(search_queries, list):
            search_queries = [article_title]
    except Exception:
        search_queries = [f"{article_title} fact check", claims[0] if claims else ""]

    web_parts = []
    for query in search_queries[:2]:
        if query.strip():
            result = web_search_tool.invoke({"query": query})
            web_parts.append(f"Search: '{query[:80]}'\n{result}")
    web_context = "\n\n".join(web_parts) if web_parts else "No web search results."

    src_result  = source_checker_tool.invoke({"domain": article_source})
    score_match = re.search(r"Score\s*:\s*([\d.]+)", src_result)
    source_score = float(score_match.group(1)) if score_match else 0.5

    return {**state,
            "rag_context": rag_context,
            "web_context": web_context,
            "source_score": source_score,
            "messages": [HumanMessage(content=f"Evidence gathered. Source score: {source_score:.2f}")]}


def verdict_generator_node(state: AgentState) -> AgentState:
    logger.info("[NODE] verdict_generator_node")
    llm = _get_llm()
    claims_text = "\n".join(f"{i}. {c}" for i,c in enumerate(state.get("claims",[]),1))

    cot_prompt = FACT_CHECK_COT_PROMPT.format(
        article_title  = state.get("article_title","Unknown"),
        article_source = state.get("article_source","Unknown"),
        article_text   = state.get("article_text","")[:2000],
        claims         = claims_text or "No claims extracted.",
        rag_context    = state.get("rag_context","No RAG evidence.")[:2000],
        web_context    = state.get("web_context","No web evidence.")[:2000],
    )

    verdict_obj  = None
    raw_response = ""
    try:
        response     = llm.invoke(cot_prompt)
        raw_response = response.content.strip().replace("```json","").replace("```","").strip()
        json_match   = re.search(r"\{[\s\S]*\}", raw_response)
        if json_match:
            raw_response = json_match.group(0)
        verdict_data = json.loads(raw_response)
        verdict_obj  = _parse_verdict(verdict_data, state)
        logger.info("Verdict: %s (%.2f)", verdict_obj.verdict, verdict_obj.confidence_score)
    except json.JSONDecodeError:
        logger.warning("JSON parse failed -- repairing...")
        verdict_obj = _repair_verdict(raw_response, state, llm)
    except Exception as e:
        logger.error("Verdict generation failed: %s", e)
        verdict_obj = _fallback_verdict(state, str(e))

    return {**state,
            "cot_reasoning": raw_response,
            "verdict_raw": raw_response,
            "verdict": verdict_obj,
            "messages": [HumanMessage(content=f"Verdict: {verdict_obj.verdict} ({verdict_obj.confidence_score:.2f})")]}


def _parse_verdict(data: dict, state: AgentState) -> FactCheckVerdict:
    verdict_map = {"real": VerdictLabel.REAL, "fake": VerdictLabel.FAKE,
                   "misleading": VerdictLabel.MISLEADING, "unverified": VerdictLabel.UNVERIFIED}
    raw_verdict    = str(data.get("verdict","unverified")).lower().strip()
    verdict        = verdict_map.get(raw_verdict, VerdictLabel.UNVERIFIED)
    confidence_raw = float(data.get("confidence_score", 0.5))
    source_score   = state.get("source_score", 0.5)
    confidence_final = max(0.05, min(0.99, (confidence_raw * 0.8) + (source_score * 0.2)))

    claims_analyzed = []
    for c in data.get("claims_analyzed", []):
        try:
            claims_analyzed.append(ClaimAnalysis(
                claim=str(c.get("claim","Unknown claim")),
                status=str(c.get("status","Unverifiable")),
                confidence=str(c.get("confidence","Low")),
                evidence=str(c.get("evidence","No evidence provided")),
            ))
        except Exception:
            continue

    if not claims_analyzed and state.get("claims"):
        claims_analyzed = [ClaimAnalysis(claim=c, status="Unverifiable",
            confidence="Low", evidence="Insufficient evidence found")
            for c in state["claims"][:3]]

    llm_sources = list(data.get("sources_consulted", []))
    all_sources = []
    seen = set()

    for src in llm_sources:
        src = src.strip()
        if src and src not in seen and not src.lower().endswith(('.com', '.org', '.net', '/', '.gov')):
             if "://" in src and src.count("/") >= 3:
                 seen.add(src)
                 all_sources.append(src)
             elif "://" not in src:
                 seen.add(src)
                 all_sources.append(src)
        elif src and src not in seen:
             seen.add(src)
             all_sources.append(src)

    if not all_sources:
        all_sources = ["None"]

    return FactCheckVerdict(
        verdict=verdict, confidence_score=round(confidence_final,2),
        claims_analyzed=claims_analyzed,
        reasoning_summary=str(data.get("reasoning_summary","Analysis complete.")),
        sources_consulted=all_sources[:5],
        cot_steps=str(data.get("cot_steps","")),
        input_type=state.get("input_type","unknown"),
        article_title=state.get("article_title",""),
    )


def _repair_verdict(raw: str, state: AgentState, llm) -> FactCheckVerdict:
    try:
        repair_prompt = VERDICT_REPAIR_PROMPT.format(raw_analysis=raw[:2000])
        response      = llm.invoke(repair_prompt)
        repaired      = response.content.strip().replace("```json","").replace("```","")
        json_match    = re.search(r"\{[\s\S]*\}", repaired)
        if json_match:
            data = json.loads(json_match.group(0))
            return _parse_verdict(data, state)
    except Exception as e:
        logger.error("Repair failed: %s", e)
    return _fallback_verdict(state, "JSON parse error")


def _fallback_verdict(state: AgentState, reason: str) -> FactCheckVerdict:
    return FactCheckVerdict(
        verdict=VerdictLabel.UNVERIFIED, confidence_score=0.1,
        claims_analyzed=[],
        reasoning_summary=f"Could not generate verdict: {reason}",
        sources_consulted=["None"],
        cot_steps="Verdict generation failed.",
        input_type=state.get("input_type","unknown"),
        article_title=state.get("article_title",""),
    )


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("input_router",       input_router_node)
    graph.add_node("claim_extractor",    claim_extractor_node)
    graph.add_node("evidence_retriever", evidence_retriever_node)
    graph.add_node("verdict_generator",  verdict_generator_node)
    graph.set_entry_point("input_router")
    graph.add_edge("input_router",       "claim_extractor")
    graph.add_edge("claim_extractor",    "evidence_retriever")
    graph.add_edge("evidence_retriever", "verdict_generator")
    graph.add_edge("verdict_generator",  END)
    compiled = graph.compile()
    logger.info("Agent graph compiled.")
    return compiled


_agent_graph = None

def get_agent():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
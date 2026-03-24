CLAIM_EXTRACTION_PROMPT = """You are an expert fact-checker and journalist.

Your task is to read the news article below and extract ALL falsifiable claims.

A FALSIFIABLE CLAIM is a specific, concrete statement that can be verified as true or false.
Examples of falsifiable claims:
   "The government announced a 10% tax cut"
   "Scientists found a new species of fish in the Amazon"
   "The situation is bad" (too vague)
   "People are worried" (not specific)

ARTICLE TEXT:
{article_text}

Return ONLY a JSON array of claim strings. No preamble. No explanation.
Example format:
["Claim 1 here", "Claim 2 here", "Claim 3 here"]

Extract between 2 and 6 claims. Focus on the most important, verifiable ones.
"""


FACT_CHECK_COT_PROMPT = """You are a senior fact-checker at an independent journalism organization.
You are rigorous, evidence-based, and never speculate beyond what the evidence shows.

You must think step-by-step before reaching any verdict.

ARTICLE TO FACT-CHECK:
Title : {article_title}
Source: {article_source}

{article_text}

STEP 1 -- CLAIM EXTRACTION:
The following falsifiable claims were extracted from the article:
{claims}

STEP 2 -- RAG EVIDENCE (from our fact-check database):
{rag_context}

STEP 3 -- WEB SEARCH EVIDENCE (live sources):
{web_context}

STEP 4 -- CLAIM-BY-CLAIM ANALYSIS:
For each claim above, analyze:
  a) Is it SUPPORTED, CONTRADICTED, or UNVERIFIABLE by the evidence?
  b) What is your confidence: HIGH, MEDIUM, or LOW?
  c) Which specific evidence supports your assessment?

Think through each claim carefully. Be explicit.

STEP 5 -- CROSS-SOURCE CONSISTENCY CHECK:
  - Do the RAG database and web search results agree?
  - Are there any contradictions between sources?
  - How credible are the sources (major news outlets vs blogs vs unknown)?
  - BE CONCISE. Avoid repetition.

STEP 6 -- FINAL VERDICT:
Based on your analysis, synthesize a final verdict.

VERDICT OPTIONS:
  Real        -- Claims are supported by credible evidence
  Fake        -- Claims are clearly contradicted by credible evidence
  Misleading  -- Claims are technically true but presented deceptively,
                missing important context, or cherry-picked
  Unverified  -- Insufficient evidence found to confirm or deny

You MUST return your response as valid JSON in EXACTLY this format:
{{
  "verdict": "Real|Fake|Misleading|Unverified",
  "confidence_score": 0.0,
  "claims_analyzed": [
    {{
      "claim": "The specific claim text",
      "status": "Supported|Contradicted|Unverifiable",
      "confidence": "High|Medium|Low",
      "evidence": "CONCISE 1-2 sentence evidence summary"
    }}
  ],
  "reasoning_summary": "CONCISE 1-2 sentence overall explanation",
  "sources_consulted": ["Up to 5 most credible full URLs"],
  "cot_steps": "CONCISE summary of reasoning steps 1-5"
}}

Respond with ONLY the JSON. No markdown. No preamble. No talk.
"""


SEARCH_QUERY_PROMPT = """You are a fact-checker generating web search queries.

Given these claims from a news article, generate the best search queries
to verify or debunk them. Think about what a journalist would search for.

CLAIMS:
{claims}

ARTICLE TITLE: {article_title}

Generate 2-3 targeted search queries. Return ONLY a JSON array of strings.
Example: ["search query 1", "search query 2", "search query 3"]

Good search queries:
  - Are specific and include key names, dates, organizations
  - Include fact-checking terms: "fact check", "debunked", "verified"
  - Try variations if the claim is about a specific event
"""


VERDICT_REPAIR_PROMPT = """The following is a fact-checking analysis that needs to be 
converted into structured JSON.

ANALYSIS TEXT:
{raw_analysis}

Convert this into valid JSON with exactly this structure:
{{
  "verdict": "Real|Fake|Misleading|Unverified",
  "confidence_score": 0.75,
  "claims_analyzed": [
    {{
      "claim": "claim text",
      "status": "Supported|Contradicted|Unverifiable", 
      "confidence": "High|Medium|Low",
      "evidence": "evidence description"
    }}
  ],
  "reasoning_summary": "2-3 sentence summary",
  "sources_consulted": ["https://example.com/article"],
  "cot_steps": "reasoning steps summary"
}}

Return ONLY valid JSON. No markdown code blocks.
"""


SOURCE_CREDIBILITY_PROMPT = """Rate the credibility of this news source on a scale of 0.0-1.0.

Source: {source_name}
URL: {url}

Consider:
- Is it a major established outlet? (BBC, Reuters, AP = high)
- Is it a known fact-checking org? (Snopes, PolitiFact = high)  
- Is it a blog, social media, or unknown site? (= low)
- Is it known for satire or bias? (= low)

Return ONLY a JSON: {{"credibility_score": 0.0, "reason": "brief reason"}}
"""
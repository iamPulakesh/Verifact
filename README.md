# News Authenticity Checker

An AI-powered system designed to analyze news headlines, paragraphs, image snapshots and URLs to mitigate misinformations. It thoroughly evaluates claims against verified fact-checks and live web search data to deliver a concrete authenticity verdict.

---
## Key Features

* **Multi-modal Input**: Accepts Live News URLs, Image Uploads (news screenshots/posters) and direct Text/Headline inputs.
* **Intelligent Claim Extraction**: Identifies the core, verifiable claims within the provided information.
* **Hybrid Verification**: Checks claims against pre-ingested fact-checks and performs live web searches for the latest context.
* **Transparent Reasoning**: Outputs a definitive verdict (True, False, Misleading, Unverified) with a confidence score, detailed reasoning, claim-by-claim breakdowns and the exact source URLs consulted.
---

## Tech Stack

* **UI**: [Streamlit](https://streamlit.io/) with custom CSS injection.
* **Agent Framework**: [LangChain](https://python.langchain.com/) and [LangGraph](https://python.langchain.com/docs/langgraph).
* **LLMs**: Open-weight and proprietary models via [Groq](https://groq.com/).
* **Information Retrieval**: 
  * [Pinecone](https://www.pinecone.io/)
  * HuggingFace `sentence-transformers`
  * [Tavily AI](https://tavily.com/)
* **Data Scraping & OCR**:
  * [EasyOCR](https://github.com/JaidedAI/EasyOCR) & [pytesseract](https://github.com/madmaze/pytesseract)
  * [Newspaper3k](https://github.com/codelucas/newspaper) & [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)

---

## Architecture Workflow

```text
       Input (Image / URL / Text)
                   │
                   ▼
             Input Router
             ┌─────┴─────┐
             │           │
          OCR Tool   URL Scraper
             └─────┬─────┘
                   │  extracted text
                   ▼
         Claim Extractor (LLM)
                   │
                   ▼
              Agent Graph
             ┌─────┴─────┐
             │           │
         RAG Search  Web Search
             └─────┬─────┘
                   │  aggregated evidence
                   ▼
           Verdict Synthesizer
                   │
                   ▼
       Structured Output (JSON)
 { verdict, confidence_score, claims_analyzed, sources }
```

---

## Project Structure

```text
├── app/
│   ├── agent/         
│   │   ├── graph.py       
│   │   ├── prompts.py     
│   │   ├── runner.py      
│   │   └── tools.py       
│   ├── models/        
│   ├── multimodal/    
│   ├── rag/           
│   ├── config.py      
│   └── main.py
├── data/            
│   ├── raw/          
├── frontend/
│   └── streamlit_app.py
├── scripts/           
├── tests/
├── .env.example
├── requirements.txt
├── .python-version
├── Dockerfile
└── README.md
```

## 📄 License
This codebase is released under the **[Apache 2.0 License](LICENSE)**.

# Verifact

Smart AI-powered system designed to analyze news headlines, paragraphs, image snapshots, and URLs to mitigate misinformation. It thoroughly evaluates claims against verified fact-checks and live web search data to deliver a concrete authenticity verdict.

---
## Key Features

* **Multi-modal Input**: Accepts Live News URLs, Image Uploads (news screenshots/posters) and direct Text/Headline inputs.
* **Intelligent Claim Extraction**: Identifies the core, verifiable claims within the provided information.
* **Hybrid Verification**: Checks claims against pre-ingested fact-checks and performs live web searches for the latest context.
* **Transparent Reasoning**: Outputs a definitive verdict (True, False, Misleading, Unverified) with a confidence score, detailed reasoning, claim-by-claim breakdowns and the exact source URLs consulted.
---

## Tech Stack

*   **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
*   **Frontend**: HTML, CSS3, and JavaScript.
*   **Agent Framework**: [LangChain](https://python.langchain.com/) and [LangGraph](https://python.langchain.com/docs/langgraph).
*   **LLMs**: Open-weight and proprietary models via multiple inference providers.
*   **Information Retrieval**: 
    *   [Pinecone](https://www.pinecone.io/)
    *   HuggingFace `sentence-transformers`
    *   [Tavily AI](https://tavily.com/) for Web Search
*   **Data Scraping & OCR**:
    *   [EasyOCR](https://github.com/JaidedAI/EasyOCR) & [pytesseract](https://github.com/madmaze/pytesseract)
    *   [Newspaper3k](https://github.com/codelucas/newspaper) & [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)

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
│   ├── api/           
│   ├── models/       
│   ├── multimodal/   
│   ├── rag/           
│   ├── config.py      
│   └── main.py        
├── frontend/
│   └── static/        
├── data/
│   ├── raw/                    
├── Dockerfile         
└── README.md
```

---

## How to run locally

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/your-username/verifact.git
    cd verifact
    ```

2.  **Set up Environment and Google CLI for Vertex AI access**:
    Create a `.env` file from the example:
    ```bash
    cp .env.example .env

    ```

3.  **Install Dependencies**:
    ```bash
    uv pip install -r requirements.txt
    ```

4.  **Start the Server**:
    ```bash
    uvicorn app.main:app --reload
    ```
    Access the UI at: `http://127.0.0.1:8000`

---

## License
This codebase is released under the **[Apache 2.0 License](LICENSE)**.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    git curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN uv pip install --system --no-cache torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

COPY --chown=user . .

EXPOSE 7860

CMD ["uvicorn", "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "7860", \
    "--workers", "1", \
    "--log-level", "info"]

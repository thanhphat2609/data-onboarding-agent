# syntax=docker/dockerfile:1
# Image for the web UI. Build context = repo root; normally built through compose:
#   docker compose -f infrastructure/compose.yaml up -d --build
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    GRADIO_ANALYTICS_ENABLED=False

# uid 1000 matches the usual host / Codespaces user, so the bind-mounted folders stay writable.
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Optional headless Chromium for web research (Bing/Brave search, JavaScript-only pages); adds ~400 MB.
#   docker compose build --build-arg WITH_BROWSER=true   (or WITH_BROWSER=true in infrastructure/.env)
ARG WITH_BROWSER=false
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN if [ "$WITH_BROWSER" = "true" ]; then \
      python -m playwright install --with-deps chromium && chmod -R a+rx /opt/ms-playwright; \
    fi

COPY --chown=app:app . .
RUN mkdir -p outputs && chown app:app outputs
USER app

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860', timeout=4)"
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "7860"]

# syntax=docker/dockerfile:1
# Image for the web UI. Build context = repo root; normally built through compose:
#   docker compose -f infrastructure/non-prod/docker-compose.yml up -d --build

# ─────────────────────────────────────────────
# Build: install the requirements into a virtualenv
# ─────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

# Only requirements.txt here, so a code change does not reinstall packages; the cache mount keeps
# downloaded wheels between builds when requirements.txt does change.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# ─────────────────────────────────────────────
# Runtime: the virtualenv + the app code, no build leftovers
# ─────────────────────────────────────────────
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="data-onboarding-agent" \
      org.opencontainers.image.description="Web UI of the Data Onboarding Agent" \
      org.opencontainers.image.source="https://github.com/thanhphat2609/data-onboarding-agent"

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

# uid 1000 matches the usual host / Codespaces user, so the bind-mounted outputs/ stays writable.
RUN useradd --create-home --uid 1000 app
COPY --from=build /opt/venv /opt/venv

# Optional headless Chromium for web research (Bing/Brave search, JavaScript-only pages); adds ~400 MB.
#   WITH_BROWSER=true in infrastructure/non-prod/.env, then up -d --build
ARG WITH_BROWSER=false
RUN if [ "$WITH_BROWSER" = "true" ]; then \
      python -m playwright install --with-deps chromium && chmod -R a+rx /opt/ms-playwright \
      && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
# Only what runs: docs, notebooks and infrastructure stay out of the image.
COPY --chown=app:app agent ./agent
COPY --chown=app:app app.py .
RUN mkdir outputs && chown app:app outputs
USER app

EXPOSE 7860
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "7860"]

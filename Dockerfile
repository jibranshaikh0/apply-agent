# apply-agent container image.
# fill.py and roles.py are Python 3.10+ stdlib-only. The browser layer
# (src/browser.py) additionally needs Playwright + Chromium, installed below.
FROM python:3.12-slim

WORKDIR /app

# Browser layer deps. Runs as root (apt needs it) and before USER app. Browsers
# go to a shared path so the unprivileged app user can launch them.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# libatomic1: Playwright's bundled driver/node needs libatomic.so.1 to start, before --with-deps can run.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && pip install --no-cache-dir playwright \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY src/ src/
COPY tests/ tests/
COPY answers/profile.template.json answers/profile.template.json
COPY README.md CLAUDE.md ./

# Playwright/Chromium are the only additions; applicant data
# (answers/profile.json) and API keys are still NEVER baked into the image.
# They are runtime inputs: bind-mount the profile and pass
# OPENAI_API_KEY as an env var. .dockerignore also keeps them out of the
# build context as a second layer of protection.
RUN useradd --create-home app && chown -R app:app /app
USER app

# Both CLIs share one image; choose per run, e.g.:
#   docker run --rm apply-agent src/roles.py --help
#   docker run --rm apply-agent src/fill.py --help
ENTRYPOINT ["python"]
CMD ["src/fill.py", "--help"]

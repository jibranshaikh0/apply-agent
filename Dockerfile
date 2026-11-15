# apply-agent container image.
# The app is Python 3.10+ stdlib-only, so the image is just a slim Python
# runtime plus the repo's code. No pip install step exists by design.
FROM python:3.12-slim

WORKDIR /app

COPY src/ src/
COPY tests/ tests/
COPY answers/profile.template.json answers/profile.template.json
COPY README.md CLAUDE.md ./

# Applicant data (answers/profile.json) and API keys are NEVER baked into
# the image. They are runtime inputs: bind-mount the profile and pass
# OPENAI_API_KEY as an env var. .dockerignore also keeps them out of the
# build context as a second layer of protection.
RUN useradd --create-home app && chown -R app:app /app
USER app

# Both CLIs share one image; choose per run, e.g.:
#   docker run --rm apply-agent src/roles.py --help
#   docker run --rm apply-agent src/fill.py --help
ENTRYPOINT ["python"]
CMD ["src/fill.py", "--help"]

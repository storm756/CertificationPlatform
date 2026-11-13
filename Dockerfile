FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    XDG_CACHE_HOME=/tmp/.cache

# WeasyPrint (certificate PDFs, Stage 7) needs Pango and HarfBuzz. The fonts it uses are our own
# bundled files; the containers run read-only, so fontconfig's cache goes to /tmp (XDG_CACHE_HOME).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt for prod images, requirements-dev.txt for the dev/test image
ARG REQUIREMENTS=requirements.txt

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r ${REQUIREMENTS}

COPY --chown=app:app . .
RUN mkdir -p /app/staticfiles /app/media && chown app:app /app/staticfiles /app/media

USER app
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3} --access-logfile - --error-logfile -"]

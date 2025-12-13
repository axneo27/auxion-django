# Multi-stage build for a lightweight Django runtime

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Keep image minimal; no apt packages needed for this project

# Copy requirements and install
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY . .

# Environment defaults
ENV DJANGO_SETTINGS_MODULE=auxion.settings \
    PYTHONPATH=/app


# Create a non-root user
RUN useradd -m django && chown -R django:django /app
USER django

# Run migrations, optionally seed CSV, then runserver (binds to default localhost)
ENV SEED_CSV=false
CMD ["sh", "-c", "python manage.py migrate && if [ \"$SEED_CSV\" = \"true\" ]; then python manage.py import_playersdata --truncate; fi && python manage.py runserver"]

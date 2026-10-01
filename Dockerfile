FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY paid_media ./paid_media
RUN pip install -r requirements.lock && pip install --no-deps . \
    && useradd --create-home --uid 10001 appuser
COPY streamlit_app.py ./
COPY .streamlit ./.streamlit
COPY data ./data
RUN mkdir -p /app/runtime && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000 8501
CMD ["uvicorn", "paid_media.api:app", "--host", "0.0.0.0", "--port", "8000"]

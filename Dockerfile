# Hype or Truth Arena (Neural Ninjas): offline labeler + claim writer. No LLM at run time.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp XDG_CACHE_HOME=/tmp/.cache
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY arena ./arena
COPY data ./data
COPY run.py .
# the frontend: python /app/web/server.py serves web/dist and runs the system live
COPY web/server.py ./web/server.py
COPY web/dist ./web/dist
COPY demo ./demo
# train the extractor statistics and the Judge's model at build time, from practice rows only
RUN python -m arena.train && python -m arena.backtest && chmod -R a+rX /app
USER 10001
EXPOSE 8000
CMD ["python", "/app/run.py"]

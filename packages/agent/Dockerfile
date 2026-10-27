FROM python:3.11-slim
WORKDIR /workspace
COPY packages/shared /workspace/packages/shared
COPY packages/agent /workspace/packages/agent
RUN pip install --no-cache-dir -e /workspace/packages/shared -e /workspace/packages/agent
RUN python -m playwright install --with-deps chromium firefox webkit
EXPOSE 8000
CMD ["uvicorn", "argus.api:app", "--host", "0.0.0.0", "--port", "8000"]

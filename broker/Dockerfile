FROM selfheal/ollama-cuda:570-0.34.4

WORKDIR /workspace

COPY broker/ /workspace/broker/
COPY pyproject.toml /workspace/pyproject.toml

RUN python3 -m pip install --no-cache-dir aiohttp

ENV PYTHONPATH=/workspace

ENTRYPOINT ["python3", "/workspace/broker/main.py"]

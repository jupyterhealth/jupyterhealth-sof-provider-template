FROM python:3.11-slim

# Interim: jupyter-smart-on-fhir is pinned to a git commit until 0.3.0a1 is on PyPI.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY provider_app ./provider_app
RUN pip install --no-cache-dir .

# The server runs as an unprivileged user. /app (code, config, notebook) stays root-owned
# and read-only to it; only HOME (Jupyter runtime dir, token files) is writable.
RUN useradd --create-home --shell /usr/sbin/nologin app
COPY jupyter_server_config.py ./
COPY dashboard.ipynb ./notebooks/
RUN chmod -R a-w /app

ENV JUPYTER_CONFIG_DIR=/app \
    NOTEBOOK_DIR=/app/notebooks \
    HOME=/home/app
USER app
EXPOSE 8888

CMD ["jupyter", "server", "--ip=0.0.0.0", "--port=8888", "--no-browser", \
     "--config=/app/jupyter_server_config.py"]
LABEL org.opencontainers.image.source https://github.com/jupyterhealth/jupyterhealth-sof-provider-template

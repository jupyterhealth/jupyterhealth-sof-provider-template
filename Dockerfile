FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY provider_app ./provider_app
RUN pip install --no-cache-dir .

COPY dashboard.ipynb jupyter_server_config.py voila.json ./

ENV JUPYTER_CONFIG_DIR=/app
EXPOSE 8888

CMD ["jupyter", "server", "--ip=0.0.0.0", "--port=8888", "--no-browser", \
     "--allow-root", "--config=/app/jupyter_server_config.py"]

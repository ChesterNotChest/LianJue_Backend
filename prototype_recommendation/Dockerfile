FROM python:3.10-slim
WORKDIR /app
COPY prototype_recommendation/ ./prototype_recommendation/
RUN pip install --no-cache-dir -r prototype_recommendation/requirements.txt
CMD ["python", "prototype_recommendation/run_demo.py"]

FROM python:3.13-slim
WORKDIR /app
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY . .
EXPOSE 8550
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8550"]

FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
COPY . .
EXPOSE 5000
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","5000"]
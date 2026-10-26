FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

RUN mkdir -p workspace data

EXPOSE 8501

CMD ["streamlit", "run", "web.py", "--server.address", "0.0.0.0", "--server.port", "8501"]

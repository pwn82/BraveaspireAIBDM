FROM python:3.13-slim

# System deps for lxml, chromadb, bcrypt
RUN apt-get update && apt-get install -y \
    gcc g++ libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create runtime dirs
RUN mkdir -p data logs vector_db

EXPOSE 8501 8000

# Default: run Streamlit
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true"]

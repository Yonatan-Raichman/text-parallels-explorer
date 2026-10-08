# Start with an environment that already has Python 3.12 installed
FROM python:3.12-slim

# Tells Docker that from now on use /app as the current working directory inside the container
WORKDIR /app

# Copy the requirements.txt file from my computer into the current working directory
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project into the current working directory inside the image
COPY . .

# Create an environment variable called DB_FILE and give it the value /data/parallels.db.
ENV DB_FILE=/data/parallels.db
RUN mkdir -p /data

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
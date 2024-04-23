# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Sets the docker container's working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    libgraphviz-dev \
    libffi-dev \  
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt requirements-dev.txt /app/
RUN CFLAGS="-I/usr/include/graphviz" \
    LDFLAGS="-L/usr/lib/graphviz" \
    pip install -r requirements-dev.txt -r requirements.txt

# Install JS packages
COPY package.json package-lock.json /app/
RUN npm install

# Add the rest of the code
COPY . /app

RUN chmod +x /app/docker-entrypoint.sh

# Define environment variable
ENV PYTHONUNBUFFERED 1

# Run migrations and start server
ENTRYPOINT ["/app/docker-entrypoint.sh"]

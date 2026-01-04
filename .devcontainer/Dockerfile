FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# Install system dependencies
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    build-essential \
    curl \
    git \
    gnupg \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install MongoDB shell (mongosh)
RUN curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor \
    && echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/debian bullseye/mongodb-org/7.0 main" | tee /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update \
    && apt-get install -y mongodb-mongosh \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# Install development tools
RUN pip install --no-cache-dir \
    black \
    pylint \
    mypy \
    pytest-cov

# Install MongoDB server (not just shell)
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends mongodb-org-server \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Create MongoDB data directory
RUN mkdir -p /data/db && chown -R vscode:vscode /data/db
# Copy devcontainer scripts
COPY .devcontainer/post-create.sh /usr/local/bin/post-create.sh
COPY .devcontainer/post-start.sh /usr/local/bin/post-start.sh
RUN chmod +x /usr/local/bin/post-create.sh /usr/local/bin/post-start.sh


# Set Python path
ENV PYTHONPATH=/workspace


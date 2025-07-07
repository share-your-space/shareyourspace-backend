# Use an official Python base image
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    # Add other necessary system dependencies here, e.g., for specific DB drivers or libraries
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Set the working directory
WORKDIR /app

# Copy only dependency files to leverage Docker cache
COPY poetry.lock pyproject.toml ./

# Install project dependencies
# --no-root: Don't install the project itself, only dependencies
# --only main: Install only the main dependencies (excluding dev, etc.)
RUN poetry install --no-root --only main --no-interaction --no-ansi

# Copy the rest of the application code
COPY ./app ./app
COPY ./scripts ./scripts
COPY ./main.py ./main.py
COPY ./test_db_connection.py ./test_db_connection.py
# Copy alembic files if migrations are run inside the container start script
COPY ./alembic.ini ./alembic.ini
COPY ./alembic ./alembic
COPY ./start.sh ./start.sh

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application using our new start script
CMD ["/app/start.sh"] 
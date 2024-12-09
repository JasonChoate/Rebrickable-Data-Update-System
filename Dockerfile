FROM python:3.9-slim

WORKDIR /app

# Install required packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts
COPY . .

# Make the update script executable
RUN chmod +x update_data.py

CMD ["python3", "update_data.py"]
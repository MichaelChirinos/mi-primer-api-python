FROM python:3.11-slim

# Instalar dependencias del sistema y herramientas de red
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Instalar Google Chrome Stable
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Instalar el ChromeDriver que coincida con la versión instalada de Chrome
RUN CHROME_VERSION=$(google-chrome --version | cut -d ' ' -f 3 | cut -d '.' -f 1) \
    && curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE" > /tmp/version.txt \
    && LATEST_VERSION=$(cat /tmp/version.txt) \
    && wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${LATEST_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip chromedriver-linux64.zip \
    && mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm -rf chromedriver-linux64.zip chromedriver-linux64

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Variables de entorno críticas
ENV ENVIRONMENT=PROD
ENV PYTHONUNBUFFERED=1
# Forzamos las rutas para que Selenium no tenga que adivinar
ENV CHROME_PATH=/usr/bin/google-chrome
ENV CHROME_DRIVER_PATH=/usr/local/bin/chromedriver

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "app:app"]

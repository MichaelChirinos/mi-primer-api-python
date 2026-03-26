FROM python:3.11-slim

# Instalar Chrome y dependencias
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Instalar ChromeDriver
RUN wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements primero (mejor caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Variables de entorno
ENV ENVIRONMENT=PROD
ENV PYTHONUNBUFFERED=1

# Exponer puerto
EXPOSE 10000

# Comando para ejecutar
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]

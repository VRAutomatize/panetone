FROM mcr.microsoft.com/playwright/python:v1.41.0-focal

# Configuração de variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Instalação de dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Configuração do diretório de trabalho
WORKDIR /app

# Cópia dos arquivos de dependências
COPY requirements.txt .

# Instalação das dependências Python e do Playwright
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install && \
    playwright install-deps chromium

# Criação dos diretórios necessários
RUN mkdir -p /app/templates /app/static

# Cópia do código da aplicação
COPY . .

# Configuração de permissões
RUN chmod -R 755 /app

# Exposição da porta
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 
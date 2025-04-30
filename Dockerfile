FROM python:3.10-slim

# Configuração de variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Instalação de dependências do sistema
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Instalação do Playwright e suas dependências
RUN pip install playwright && \
    playwright install --with-deps chromium

# Configuração do diretório de trabalho
WORKDIR /app

# Cópia dos arquivos de dependências
COPY requirements.txt .

# Instalação das dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Cópia do código da aplicação
COPY . .

# Exposição da porta
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 
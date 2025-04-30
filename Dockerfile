FROM mcr.microsoft.com/playwright/python:v1.41.0-focal

# Configuração de variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Configuração do diretório de trabalho
WORKDIR /app

# Cópia dos arquivos de dependências
COPY requirements.txt .

# Instalação das dependências Python e do Playwright
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install && \
    playwright install-deps

# Cópia do código da aplicação
COPY . .

# Exposição da porta
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 
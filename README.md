# API de Automação Banco Pan Veículos

Este projeto implementa uma API RESTful para automatizar o processo de login e verificação de elegibilidade de clientes no site do Banco Pan Veículos.

## Requisitos

- Python 3.10+
- Docker (opcional, para execução em container)

## Instalação

### Método 1: Execução Local

1. Clone o repositório:
```bash
git clone <url-do-repositorio>
cd panetone
```

2. Crie um ambiente virtual e ative-o:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Instale as dependências do Playwright:
```bash
playwright install --with-deps chromium
```

### Método 2: Execução com Docker

1. Construa a imagem:
```bash
docker build -t panetone .
```

2. Execute o container:
```bash
docker run -p 8000:8000 panetone
```

## Uso

A API expõe dois endpoints principais:

### 1. Iniciar Verificação

```http
POST /run
Content-Type: application/json

{
    "login": "seu_login",
    "senha": "sua_senha",
    "cpf_do_cliente": "12345678900"
}
```

Resposta:
```json
{
    "run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2. Verificar Status

```http
GET /status/{run_id}
```

Resposta:
```json
{
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "result": "Cliente Elegível",
    "log_summary": "Log detalhado da execução..."
}
```

## Configuração

O serviço pode ser configurado através de variáveis de ambiente:

- `LOGIN_URL`: URL do site de login (default: https://veiculos.bancopan.com.br/login)
- `MAX_CONCURRENT_RUNS`: Número máximo de execuções concorrentes (default: número de cores da CPU - 1)

## Logs

Os logs são exibidos no console e incluem:
- Timestamp
- Nível do log
- Mensagem detalhada
- ID da execução (run_id)

## Segurança

- As credenciais são processadas apenas em memória
- O serviço opera em modo headless
- Cada execução usa um contexto isolado do navegador

## Limitações

- O estado das execuções é mantido em memória
- Reiniciar o serviço limpa o histórico de execuções
- O número máximo de execuções concorrentes é limitado pelos recursos da máquina 
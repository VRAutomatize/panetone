# 🥖 Panetone

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-green.svg)
![Playwright](https://img.shields.io/badge/Playwright-1.41.2-orange.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

<div align="center">
  <img src="https://res.cloudinary.com/dm7cgwtmp/image/upload/v1740567841/VR%20Automatize/logoVR.png" alt="VR Automatize Logo" width="200"/>
  <h3>Sistema de Automação Inteligente</h3>
  <p>Desenvolvido por VR Automatize</p>
</div>

## 📋 Sobre

O Panetone é um sistema de automação robusto e eficiente, projetado para verificar elegibilidade em sistemas web de forma automatizada. Com gerenciamento inteligente de recursos e interface moderna, o sistema oferece uma solução completa para automação de processos.

### ✨ Características Principais

- 🤖 Automação inteligente com Playwright
- 📊 Dashboard em tempo real
- 🔄 Gerenciamento automático de recursos
- 🎯 Sistema de retry inteligente
- 🌐 Interface web moderna e responsiva
- 📱 Design adaptativo para dispositivos móveis

## 🚀 Tecnologias

- **Backend:**
  - Python 3.8+
  - FastAPI
  - Playwright
  - Psutil
  - Python-dotenv

- **Frontend:**
  - HTML5
  - CSS3
  - JavaScript
  - Chart.js

## 💻 Requisitos do Sistema

- Python 3.8 ou superior
- Docker (opcional)
- 500MB de RAM por instância
- 0.5 núcleo de CPU por instância

## 🛠️ Instalação

### Usando Docker

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/panetone.git
cd panetone

# Construa a imagem
docker build -t panetone .

# Execute o container
docker run -p 8000:8000 panetone
```

### Instalação Local

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/panetone.git
cd panetone

# Crie um ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\\Scripts\\activate   # Windows

# Instale as dependências
pip install -r requirements.txt

# Execute o sistema
python main.py
```

## 🖥️ Uso

1. Acesse o dashboard em `http://localhost:8000`
2. O sistema iniciará automaticamente o gerenciamento de recursos
3. Monitore as instâncias ativas através do dashboard
4. Visualize em tempo real:
   - Uso de CPU
   - Consumo de memória
   - Instâncias ativas
   - Tempo de execução de cada instância

## 📊 Dashboard

O dashboard oferece uma interface moderna com:

- 🌙 Tema escuro com detalhes em amarelo
- 🎨 Efeitos glassmorphism
- 📈 Gráficos de CPU e memória
- 📋 Lista de instâncias ativas
- 🔄 Atualização automática a cada 5 segundos
- 📱 Interface totalmente responsiva

## 🔧 Configuração

O sistema pode ser configurado através de variáveis de ambiente:

```env
LOGIN_URL=https://seu-sistema.com/login
MAX_CONCURRENT_RUNS=4  # Opcional, calculado automaticamente
```

## 📁 Estrutura do Projeto

```
panetone/
├── automation.py      # Lógica principal de automação
├── main.py           # Servidor FastAPI e rotas
├── requirements.txt  # Dependências do projeto
├── Dockerfile        # Configuração Docker
├── templates/        # Templates HTML
│   └── dashboard.html
├── static/          # Arquivos estáticos
│   └── style.css
└── README.md
```

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor, sinta-se à vontade para enviar um Pull Request.

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👥 Autores

- VR Automatize

---

<div align="center">
  <p>Desenvolvido com ❤️ por VR Automatize</p>
</div>

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

#   p a n e t o n e 
 
 
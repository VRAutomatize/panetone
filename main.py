import asyncio
import logging
import os
import uuid
from typing import Dict, Optional, Set
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psutil
from dotenv import load_dotenv
from automation import run_automation

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv()

# Configurações
MAX_CONCURRENT_RUNS = max(1, psutil.cpu_count(logical=True) - 1)
LOGIN_URL = os.getenv("LOGIN_URL", "https://veiculos.bancopan.com.br/login")

# Estruturas de dados para gerenciamento de estado
active_runs: Set[str] = set()
queued_tasks: asyncio.Queue = asyncio.Queue()
run_results: Dict[str, dict] = {}

app = FastAPI(title="Banco Pan Veículos Automation API")

class RunRequest(BaseModel):
    login: str
    senha: str
    cpf_do_cliente: str

class RunResponse(BaseModel):
    run_id: str

class StatusResponse(BaseModel):
    run_id: str
    status: str
    result: Optional[str] = None
    log_summary: Optional[str] = None
    screenshot: Optional[str] = None

async def automation_task(run_id: str, login: str, senha: str, cpf_do_cliente: str):
    """
    Função principal de automação
    """
    try:
        logger.info(f"[{run_id}] Iniciando automação")
        result = await run_automation(run_id, login, senha, cpf_do_cliente)
        
        run_results[run_id].update({
            "status": "completed",
            "result": result["result"],
            "log_summary": result["log_summary"],
            "screenshot": result.get("screenshot")
        })
    except Exception as e:
        logger.error(f"[{run_id}] Erro na automação: {str(e)}")
        run_results[run_id].update({
            "status": "failed",
            "result": f"Erro: {str(e)}",
            "log_summary": f"Falha na execução: {str(e)}",
            "screenshot": None
        })
    finally:
        active_runs.remove(run_id)
        await process_queue()

async def process_queue():
    """
    Processa a fila de tarefas pendentes
    """
    while not queued_tasks.empty() and len(active_runs) < MAX_CONCURRENT_RUNS:
        task = await queued_tasks.get()
        run_id, login, senha, cpf_do_cliente = task
        active_runs.add(run_id)
        run_results[run_id]["status"] = "running"
        asyncio.create_task(automation_task(run_id, login, senha, cpf_do_cliente))

@app.post("/run", response_model=RunResponse)
async def create_run(request: RunRequest):
    run_id = str(uuid.uuid4())
    logger.info(f"[{run_id}] Nova requisição recebida")
    
    run_results[run_id] = {"status": "pending"}
    
    if len(active_runs) < MAX_CONCURRENT_RUNS:
        active_runs.add(run_id)
        run_results[run_id]["status"] = "running"
        asyncio.create_task(automation_task(
            run_id, request.login, request.senha, request.cpf_do_cliente
        ))
    else:
        await queued_tasks.put((run_id, request.login, request.senha, request.cpf_do_cliente))
        run_results[run_id]["status"] = "queued"
    
    return RunResponse(run_id=run_id)

@app.get("/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str):
    if run_id not in run_results:
        raise HTTPException(status_code=404, detail="Run ID não encontrado")
    
    result = run_results[run_id]
    return StatusResponse(
        run_id=run_id,
        status=result["status"],
        result=result.get("result"),
        log_summary=result.get("log_summary"),
        screenshot=result.get("screenshot")
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
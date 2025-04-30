import asyncio
import logging
from typing import Dict, Tuple, Optional
from playwright.async_api import async_playwright, Browser, Page, TimeoutError

logger = logging.getLogger(__name__)

class AutomationError(Exception):
    pass

class PanAutomation:
    def __init__(self, login_url: str):
        self.login_url = login_url
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()

    async def initialize(self):
        """Inicializa o navegador e cria uma nova página"""
        if not self.browser:
            raise AutomationError("Browser não inicializado")
        
        self.page = await self.browser.new_page()
        await self.page.set_viewport_size({"width": 1280, "height": 720})

    async def login(self, login: str, senha: str) -> None:
        """Realiza o login no sistema"""
        try:
            await self.page.goto(self.login_url)
            logger.info("Navegando para página de login")

            # Aguarda e preenche o campo de login
            await self.page.wait_for_selector('input[name="login"]', state="visible")
            await self.page.fill('input[name="login"]', login)
            logger.info("Campo de login preenchido")

            # Aguarda e preenche o campo de senha
            await self.page.wait_for_selector('input[name="password"]', state="visible")
            await self.page.fill('input[name="password"]', senha)
            logger.info("Campo de senha preenchido")

            # Clica no botão de login
            await self.page.click('span.pan-mahoe-button__wrapper')
            logger.info("Botão de login clicado")

            # Aguarda a navegação após o login
            await self.page.wait_for_load_state("networkidle")
            logger.info("Login realizado com sucesso")

        except TimeoutError as e:
            logger.error(f"Timeout durante o login: {str(e)}")
            raise AutomationError("Timeout ao tentar fazer login")
        except Exception as e:
            logger.error(f"Erro durante o login: {str(e)}")
            raise AutomationError(f"Falha no login: {str(e)}")

    async def verificar_elegibilidade(self, cpf: str) -> Tuple[str, str]:
        """
        Verifica a elegibilidade do cliente usando o CPF
        Retorna uma tupla com (resultado, log_summary)
        """
        try:
            # Aguarda e preenche o campo de CPF
            await self.page.wait_for_selector('input[name="cpf"]', state="visible")
            await self.page.fill('input[name="cpf"]', cpf)
            logger.info("Campo de CPF preenchido")

            # Clica no botão de avançar
            await self.page.click('div.mahoe-ripple')
            logger.info("Botão de avançar clicado")

            # Aguarda o resultado aparecer
            # Vamos esperar por qualquer um dos textos possíveis
            try:
                await self.page.wait_for_selector('text="Cliente Elegível"', timeout=10000)
                return "Cliente Elegível", "Cliente verificado como elegível"
            except TimeoutError:
                try:
                    await self.page.wait_for_selector('text="Cliente Não Elegível"', timeout=10000)
                    return "Cliente Não Elegível", "Cliente verificado como não elegível"
                except TimeoutError:
                    return "Resultado Indeterminado", "Não foi possível determinar a elegibilidade do cliente"

        except TimeoutError as e:
            logger.error(f"Timeout durante verificação de elegibilidade: {str(e)}")
            raise AutomationError("Timeout ao tentar verificar elegibilidade")
        except Exception as e:
            logger.error(f"Erro durante verificação de elegibilidade: {str(e)}")
            raise AutomationError(f"Falha na verificação: {str(e)}")

async def run_automation(run_id: str, login: str, senha: str, cpf: str) -> Dict[str, str]:
    """
    Função principal que executa todo o fluxo de automação
    """
    log_summary = []
    
    try:
        async with PanAutomation(login_url="https://veiculos.bancopan.com.br/login") as automation:
            log_summary.append("Iniciando automação")
            
            await automation.initialize()
            log_summary.append("Navegador inicializado")
            
            await automation.login(login, senha)
            log_summary.append("Login realizado com sucesso")
            
            result, verification_log = await automation.verificar_elegibilidade(cpf)
            log_summary.append(verification_log)
            
            return {
                "result": result,
                "log_summary": "\n".join(log_summary)
            }
            
    except AutomationError as e:
        log_summary.append(f"Erro na automação: {str(e)}")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary)
        }
    except Exception as e:
        log_summary.append(f"Erro inesperado: {str(e)}")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary)
        } 
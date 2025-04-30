import asyncio
import logging
from typing import Dict, Tuple, Optional
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
from functools import wraps
import time

logger = logging.getLogger(__name__)

class AutomationError(Exception):
    pass

def retry_on_failure(max_retries=3, delay=2):
    """
    Decorator para implementar retry em caso de falha
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Tentativa {attempt + 1} falhou: {str(e)}. Tentando novamente em {delay} segundos...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Todas as {max_retries} tentativas falharam. Último erro: {str(e)}")
                        raise AutomationError(f"Falha após {max_retries} tentativas: {str(e)}")
            raise last_error
        return wrapper
    return decorator

class PanAutomation:
    def __init__(self, login_url: str):
        self.login_url = login_url
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.context = None

    async def __aenter__(self):
        logger.info("Iniciando Playwright e configurando navegador...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        logger.info("Navegador Chromium iniciado com sucesso")
        
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ignore_https_errors=True
        )
        logger.info("Contexto do navegador criado com sucesso")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("Finalizando recursos do navegador...")
        if self.context:
            await self.context.close()
            logger.info("Contexto do navegador fechado")
        if self.browser:
            await self.browser.close()
            logger.info("Navegador fechado")

    async def initialize(self):
        """Inicializa o navegador e cria uma nova página"""
        if not self.browser:
            raise AutomationError("Browser não inicializado")
        
        logger.info("Criando nova página no navegador...")
        self.page = await self.context.new_page()
        
        # Configurar timeouts mais curtos
        self.page.set_default_timeout(10000)  # 10 segundos
        self.page.set_default_navigation_timeout(10000)
        logger.info("Timeouts configurados: 10 segundos para navegação e operações")

        # Configurar viewport e user agent
        await self.page.set_viewport_size({"width": 1280, "height": 720})
        await self.page.set_extra_http_headers({
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
        })

    async def _try_selectors(self, selectors: list[str], timeout: int = 10000) -> Optional[Page]:
        """
        Tenta diferentes seletores até encontrar um que funcione
        """
        for selector in selectors:
            try:
                logger.info(f"Tentando seletor: {selector}")
                element = await self.page.wait_for_selector(
                    selector,
                    state="visible",
                    timeout=timeout
                )
                if element:
                    logger.info(f"Seletor encontrado com sucesso: {selector}")
                    return element
            except TimeoutError:
                logger.debug(f"Seletor não encontrado: {selector}")
                continue
        return None

    @retry_on_failure(max_retries=3, delay=1)
    async def login(self, login: str, senha: str) -> None:
        """Realiza o login no sistema"""
        try:
            # Navegação com retry
            logger.info(f"Iniciando navegação para {self.login_url}")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de navegação...")
                    response = await self.page.goto(
                        self.login_url,
                        wait_until='domcontentloaded',
                        timeout=10000
                    )
                    
                    if not response:
                        raise TimeoutError("Falha ao carregar a página")
                    
                    if response.status != 200:
                        raise AutomationError(f"Erro ao carregar página: status {response.status}")
                    
                    logger.info("Página carregada inicialmente")
                    
                    try:
                        await self.page.wait_for_selector('body', state='visible', timeout=5000)
                        logger.info("Corpo da página visível")
                    except TimeoutError:
                        logger.warning("Corpo da página não está visível, tentando recarregar...")
                        continue

                    current_url = self.page.url
                    logger.info(f"Navegação bem-sucedida. URL atual: {current_url}")
                    break
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de navegação, tentando novamente...")
                    await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao carregar a página de login após várias tentativas")

            # Lista de possíveis seletores para o campo de login
            login_selectors = [
                'input[name="login"]',
                'input[formcontrolname="login"]',
                'input[type="text"][placeholder*="login" i]',
                'input[type="text"][placeholder*="usuário" i]',
                'input[type="text"][placeholder*="cpf" i]'
            ]

            # Aguarda e preenche o campo de login com retry
            logger.info("Procurando campo de login...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar campo de login...")
                    login_field = await self._try_selectors(login_selectors)
                    
                    if not login_field:
                        raise TimeoutError("Campo de login não encontrado com nenhum seletor")
                    
                    await login_field.fill(login)
                    logger.info("Campo de login localizado e preenchido com sucesso")
                    break
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de localizar campo de login...")
                    if attempt == 1:
                        logger.info("Tentando recarregar a página...")
                        await self.page.reload(wait_until='domcontentloaded')
                        await asyncio.sleep(1)
                    else:
                        await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao preencher campo de login após várias tentativas")

            # Lista de possíveis seletores para o campo de senha
            password_selectors = [
                'input.pan-mahoe-input-element.mh-input-element[formcontrolname="senha"]',
                'input.pan-mahoe-input-element.mh-input-element[name="password"]',
                'input.login__form__input--hiden[name="password"]',
                'input[formcontrolname="senha"][name="password"]',
                'input.pan-mahoe-input-element[name="password"]',
                'input.mh-input-element[name="password"]',
                'input[name="password"]',
                'input[type="password"]',
                'input[formcontrolname="senha"]',
                'input[type="password"][placeholder*="senha" i]'
            ]

            # Aguarda e preenche o campo de senha com retry
            logger.info("Procurando campo de senha...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar campo de senha...")
                    password_field = await self._try_selectors(password_selectors)
                    
                    if not password_field:
                        raise TimeoutError("Campo de senha não encontrado com nenhum seletor")
                    
                    await password_field.fill(senha)
                    logger.info("Campo de senha localizado e preenchido com sucesso")
                    break
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de localizar campo de senha...")
                    if attempt == 1:
                        logger.info("Tentando recarregar a página...")
                        await self.page.reload(wait_until='domcontentloaded')
                        await asyncio.sleep(1)
                    else:
                        await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao preencher campo de senha após várias tentativas")

            # Lista de possíveis seletores para o botão de login
            button_selectors = [
                'span.pan-mahoe-button__wrapper',
                'button[type="submit"]',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
                'button:has-text("Acessar")',
                'button.login-button',
                'button[formcontrolname="submit"]'
            ]

            # Clica no botão de login com retry
            logger.info("Procurando botão de login...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar botão de login...")
                    login_button = await self._try_selectors(button_selectors)
                    
                    if not login_button:
                        raise TimeoutError("Botão de login não encontrado com nenhum seletor")
                    
                    await login_button.click()
                    logger.info("Botão de login localizado e clicado com sucesso")
                    break
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de localizar botão de login...")
                    if attempt == 1:
                        logger.info("Tentando recarregar a página...")
                        await self.page.reload(wait_until='domcontentloaded')
                        await asyncio.sleep(1)
                    else:
                        await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao clicar no botão de login após várias tentativas")

            # Aguarda a navegação após o login
            logger.info("Aguardando carregamento após login...")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
                current_url = self.page.url
                logger.info(f"Login realizado com sucesso. URL atual: {current_url}")
            except TimeoutError:
                current_url = self.page.url
                logger.warning(f"Timeout ao aguardar carregamento após login, mas continuando... URL atual: {current_url}")

        except TimeoutError as e:
            logger.error(f"Timeout durante o login: {str(e)}")
            raise AutomationError("Timeout ao tentar fazer login")
        except Exception as e:
            logger.error(f"Erro durante o login: {str(e)}")
            raise AutomationError(f"Falha no login: {str(e)}")

    @retry_on_failure(max_retries=3, delay=2)
    async def verificar_elegibilidade(self, cpf: str) -> Tuple[str, str]:
        """
        Verifica a elegibilidade do cliente usando o CPF
        Retorna uma tupla com (resultado, log_summary)
        """
        try:
            logger.info("Iniciando verificação de elegibilidade...")
            current_url = self.page.url
            logger.info(f"URL atual antes da verificação: {current_url}")

            # Aguarda e preenche o campo de CPF
            logger.info("Procurando campo de CPF...")
            await self.page.wait_for_selector('input[name="cpf"]', state="visible")
            await self.page.fill('input[name="cpf"]', cpf)
            logger.info("Campo de CPF localizado e preenchido com sucesso")

            # Clica no botão de avançar
            logger.info("Procurando botão de avançar...")
            await self.page.click('div.mahoe-ripple')
            logger.info("Botão de avançar clicado com sucesso")

            # Aguarda o resultado aparecer
            logger.info("Aguardando resultado da verificação...")
            try:
                await self.page.wait_for_selector('text="Cliente Elegível"', timeout=10000)
                logger.info("Cliente verificado como elegível")
                return "Cliente Elegível", "Cliente verificado como elegível"
            except TimeoutError:
                try:
                    await self.page.wait_for_selector('text="Cliente Não Elegível"', timeout=10000)
                    logger.info("Cliente verificado como não elegível")
                    return "Cliente Não Elegível", "Cliente verificado como não elegível"
                except TimeoutError:
                    logger.warning("Não foi possível determinar a elegibilidade do cliente")
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
    start_time = time.time()
    
    try:
        async with PanAutomation(login_url="https://veiculos.bancopan.com.br/login") as automation:
            log_summary.append("Iniciando automação")
            
            await automation.initialize()
            log_summary.append("Navegador inicializado")
            
            await automation.login(login, senha)
            log_summary.append("Login realizado com sucesso")
            
            result, verification_log = await automation.verificar_elegibilidade(cpf)
            log_summary.append(verification_log)
            
            execution_time = time.time() - start_time
            log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
            
            return {
                "result": result,
                "log_summary": "\n".join(log_summary)
            }
            
    except AutomationError as e:
        log_summary.append(f"Erro na automação: {str(e)}")
        execution_time = time.time() - start_time
        log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary)
        }
    except Exception as e:
        log_summary.append(f"Erro inesperado: {str(e)}")
        execution_time = time.time() - start_time
        log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary)
        } 
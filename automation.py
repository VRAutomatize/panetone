import asyncio
import logging
import psutil
import math
from typing import Dict, Tuple, Optional, List, Any, Set
from playwright.async_api import async_playwright, Browser, Page, TimeoutError
from functools import wraps
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

@dataclass
class SystemResources:
    cpu_cores: int
    total_memory_gb: float
    available_memory_gb: float
    
class ResourceManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ResourceManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        self.active_instances: Set[str] = set()
        self.last_resource_check = 0
        self.resource_check_interval = 10  # Verifica recursos a cada 10 segundos
        self.update_system_resources()
        
        # Configurações base por instância
        self.memory_per_instance_gb = 0.5  # 500MB por instância
        self.cpu_per_instance = 0.5  # Meio núcleo por instância
        
        # Calcula limites iniciais
        self._calculate_limits()
        
        logger.info(f"Resource Manager iniciado. Limite de instâncias: {self.max_instances}")
    
    def update_system_resources(self) -> SystemResources:
        """Atualiza informações sobre recursos do sistema"""
        cpu_cores = psutil.cpu_count(logical=True)
        memory = psutil.virtual_memory()
        total_memory = memory.total / (1024 ** 3)  # GB
        available_memory = memory.available / (1024 ** 3)  # GB
        
        # Calcula uso atual de CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        
        self.system_resources = SystemResources(
            cpu_cores=cpu_cores,
            total_memory_gb=total_memory,
            available_memory_gb=available_memory
        )
        
        logger.info(f"Recursos atualizados - CPU: {cpu_percent}%, Memória Total: {total_memory:.1f}GB, Disponível: {available_memory:.1f}GB")
        return self.system_resources
    
    def _calculate_limits(self):
        """Calcula o número máximo de instâncias com base nos recursos"""
        # Hardcap de 2 instâncias
        self.max_instances = 2
        
        logger.info(f"Limites atualizados - Hardcap: 2 instâncias")
    
    async def check_resources(self):
        """Verifica se é necessário atualizar os limites de recursos"""
        current_time = time.time()
        if current_time - self.last_resource_check > self.resource_check_interval:
            self.update_system_resources()
            self._calculate_limits()
            self.last_resource_check = current_time
    
    async def acquire_instance(self, instance_id: str) -> bool:
        """Tenta adquirir uma vaga para uma nova instância"""
        await self.check_resources()
        
        with self._lock:
            if len(self.active_instances) >= self.max_instances:
                logger.warning(f"Limite de instâncias atingido ({self.max_instances}). Instância {instance_id} em espera.")
                return False
            
            self.active_instances.add(instance_id)
            logger.info(f"Instância {instance_id} iniciada. Total ativo: {len(self.active_instances)}/{self.max_instances}")
            return True
    
    def release_instance(self, instance_id: str):
        """Libera uma instância"""
        with self._lock:
            self.active_instances.discard(instance_id)
            logger.info(f"Instância {instance_id} finalizada. Total ativo: {len(self.active_instances)}/{self.max_instances}")
            # Força uma atualização dos recursos após liberar uma instância
            self.update_system_resources()
            self._calculate_limits()

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
        self.playwright = None

    async def __aenter__(self):
        logger.info("Iniciando Playwright e configurando navegador...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
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
        try:
            if self.page:
                await self.page.close()
                logger.info("Página fechada")
            if self.context:
                await self.context.close()
                logger.info("Contexto do navegador fechado")
            if self.browser:
                await self.browser.close()
                logger.info("Navegador fechado")
            if self.playwright:
                await self.playwright.stop()
                logger.info("Playwright finalizado")
        except Exception as e:
            logger.error(f"Erro ao finalizar recursos: {str(e)}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

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

    async def _try_fill_input(self, element, value: str, max_attempts: int = 3, is_cpf: bool = False) -> bool:
        """
        Tenta preencher um campo de input usando diferentes estratégias
        """
        for attempt in range(max_attempts):
            try:
                # Tenta focar o elemento primeiro
                await element.focus()
                await asyncio.sleep(0.5)
                
                # Se for CPF, vamos tentar algumas estratégias específicas primeiro
                if is_cpf:
                    # Estratégia 1: Preencher dígito por dígito com delay
                    try:
                        # Limpa o campo
                        await element.evaluate('(element) => { element.value = ""; }')
                        await asyncio.sleep(0.2)
                        
                        # Remove pontuação do CPF se houver
                        cpf_digits = ''.join(filter(str.isdigit, value))
                        
                        # Digita cada número com um pequeno delay
                        for digit in cpf_digits:
                            await element.type(digit, delay=100)
                            await asyncio.sleep(0.1)
                        
                        # Verifica se o valor foi preenchido corretamente
                        actual_value = await element.evaluate('(element) => element.value')
                        if len(''.join(filter(str.isdigit, actual_value))) == 11:
                            return True
                    except Exception as e:
                        logger.debug(f"Falha na estratégia 1 (CPF dígito a dígito): {str(e)}")

                    # Estratégia 2: Usar JavaScript para simular eventos de input
                    try:
                        script = """
                        (element, value) => {
                            element.value = value;
                            element.dispatchEvent(new Event('input', { bubbles: true }));
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                            return element.value;
                        }
                        """
                        # Tenta com o valor formatado
                        formatted_cpf = f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
                        result = await element.evaluate(script, formatted_cpf)
                        if len(''.join(filter(str.isdigit, result))) == 11:
                            return True
                            
                        # Se falhou, tenta com o valor sem formatação
                        result = await element.evaluate(script, value)
                        if len(''.join(filter(str.isdigit, result))) == 11:
                            return True
                    except Exception as e:
                        logger.debug(f"Falha na estratégia 2 (CPF via JavaScript): {str(e)}")

                # Estratégias padrão para outros campos
                # Estratégia 3: Usando fill
                try:
                    await element.fill(value)
                    actual_value = await element.evaluate('(element) => element.value')
                    if actual_value == value:
                        return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 3 (fill): {str(e)}")

                # Estratégia 4: Usando type
                try:
                    await element.type(value, delay=50)
                    actual_value = await element.evaluate('(element) => element.value')
                    if actual_value == value:
                        return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 4 (type): {str(e)}")

                # Estratégia 5: JavaScript direto
                try:
                    await element.evaluate(f'(element) => {{ element.value = "{value}"; }}')
                    await element.evaluate('(element) => element.dispatchEvent(new Event("input"))')
                    await element.evaluate('(element) => element.dispatchEvent(new Event("change"))')
                    actual_value = await element.evaluate('(element) => element.value')
                    if actual_value == value:
                        return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 5 (JavaScript): {str(e)}")

                if attempt < max_attempts - 1:
                    logger.warning(f"Tentativa {attempt + 1} de preencher o campo falhou, tentando novamente...")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Erro ao tentar preencher campo: {str(e)}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1)
                continue
        
        return False

    async def _try_selectors(self, selectors: List[str], timeout: int = 10000) -> Optional[Page]:
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

    async def _try_click_button(self, element, max_attempts: int = 3) -> bool:
        """
        Tenta clicar em um botão usando diferentes estratégias
        """
        for attempt in range(max_attempts):
            try:
                # Tenta rolar até o elemento primeiro
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)

                # Estratégia 1: Clique direto do Playwright
                try:
                    await element.click(timeout=5000)
                    return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 1 (click direto): {str(e)}")

                # Estratégia 2: Clique via JavaScript
                try:
                    await element.evaluate('(element) => element.click()')
                    return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 2 (JavaScript click): {str(e)}")

                # Estratégia 3: Procurar o botão pai se for um span
                try:
                    button = await element.evaluate('(element) => element.closest("button")')
                    if button:
                        await self.page.evaluate('(button) => button.click()', button)
                        return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 3 (botão pai): {str(e)}")

                # Estratégia 4: Dispatch de eventos
                try:
                    await element.evaluate('''(element) => {
                        element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        element.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    }''')
                    return True
                except Exception as e:
                    logger.debug(f"Falha na estratégia 4 (dispatch eventos): {str(e)}")

                if attempt < max_attempts - 1:
                    logger.warning(f"Tentativa {attempt + 1} de clicar falhou, tentando novamente...")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Erro ao tentar clicar: {str(e)}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(1)
                continue
        
        return False

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
                    
                    # Aguarda o corpo da página estar visível
                    await self.page.wait_for_selector('body', state='visible', timeout=5000)
                    logger.info("Corpo da página visível")
                    
                    # Trata o popup de cookies imediatamente após a página carregar
                    logger.info("Verificando popup de cookies...")
                    cookie_button_selectors = [
                        '#onetrust-accept-btn-handler',  # Seletor específico do botão
                        'button[aria-label="Permitir todos os cookies"]',
                        'button:has-text("Permitir todos os cookies")',
                        'button:has-text("Got it!")',
                        'button:has-text("Aceitar")',
                        'button:has-text("Accept All")',
                        '[aria-label="Aceitar cookies"]'
                    ]
                    
                    # Aguarda um momento para o popup aparecer
                    await asyncio.sleep(1)
                    
                    for selector in cookie_button_selectors:
                        try:
                            logger.info(f"Tentando clicar no botão de cookies com seletor: {selector}")
                            cookie_button = await self.page.wait_for_selector(selector, timeout=3000, state="visible")
                            if cookie_button:
                                # Tenta clicar usando diferentes estratégias
                                try:
                                    await cookie_button.click()
                                except Exception as e:
                                    logger.debug(f"Falha no clique direto: {str(e)}, tentando via JavaScript")
                                    await self.page.evaluate("""(selector) => {
                                        const button = document.querySelector(selector);
                                        if (button) button.click();
                                    }""", selector)
                                
                                logger.info("Popup de cookies fechado com sucesso")
                                await asyncio.sleep(1)  # Aguarda a animação do popup
                                break
                        except Exception as e:
                            logger.debug(f"Falha ao tentar seletor {selector}: {str(e)}")
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
                    
                    if await self._try_fill_input(login_field, login):
                        logger.info("Campo de login localizado e preenchido com sucesso")
                        break
                    else:
                        raise TimeoutError("Não foi possível preencher o campo de login")
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
                    
                    # Tenta preencher usando diferentes estratégias
                    if await self._try_fill_input(password_field, senha):
                        logger.info("Campo de senha localizado e preenchido com sucesso")
                        break
                    else:
                        raise TimeoutError("Não foi possível preencher o campo de senha")
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
                'button[type="submit"]',
                'button.pan-mahoe-button',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
                'button:has-text("Acessar")',
                'button.login-button',
                'button[formcontrolname="submit"]',
                'span.pan-mahoe-button__wrapper',
                '.pan-mahoe-button__wrapper',
                'button.pan-mahoe-button__wrapper'
            ]

            # Clica no botão de login com retry
            logger.info("Procurando botão de login...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar botão de login...")
                    login_button = await self._try_selectors(button_selectors)
                    
                    if not login_button:
                        raise TimeoutError("Botão de login não encontrado com nenhum seletor")
                    
                    # Tenta clicar usando diferentes estratégias
                    if await self._try_click_button(login_button):
                        logger.info("Botão de login localizado e clicado com sucesso")
                        break
                    else:
                        raise TimeoutError("Não foi possível clicar no botão de login")
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

    async def _find_element_smart(self, context_description: str, strategies: List[Dict[str, Any]], required: bool = True) -> Optional[Any]:
        """
        Método inteligente para encontrar elementos usando múltiplas estratégias
        """
        for strategy in strategies:
            try:
                if strategy.get("type") == "js":
                    # Estratégia JavaScript
                    result = await self.page.evaluate(strategy["script"])
                    if result:
                        logger.info(f"{context_description} encontrado via JavaScript")
                        return result
                elif strategy.get("type") == "selector":
                    # Estratégia de seletor
                    element = await self.page.wait_for_selector(
                        strategy["selector"],
                        timeout=strategy.get("timeout", 2000)
                    )
                    if element:
                        logger.info(f"{context_description} encontrado via seletor: {strategy['selector']}")
                        return element
                elif strategy.get("type") == "xpath":
                    # Estratégia XPath
                    element = await self.page.wait_for_selector(
                        f"xpath={strategy['xpath']}",
                        timeout=strategy.get("timeout", 2000)
                    )
                    if element:
                        logger.info(f"{context_description} encontrado via XPath")
                        return element
            except Exception as e:
                continue
        
        if required:
            raise AutomationError(f"Não foi possível encontrar {context_description}")
        return None

    @retry_on_failure(max_retries=3, delay=2)
    async def verificar_elegibilidade(self, cpf: str) -> Tuple[str, str, Optional[str]]:
        """
        Verifica a elegibilidade do cliente usando o CPF
        Retorna uma tupla com (resultado, log_summary, screenshot_base64)
        """
        screenshot_base64 = None
        try:
            logger.info("Iniciando verificação de elegibilidade...")
            
            # Tenta lidar com o popup de cookies primeiro
            logger.info("Verificando popup de cookies...")
            cookie_button_selectors = [
                '#onetrust-accept-btn-handler',  # Seletor específico do botão
                'button[aria-label="Permitir todos os cookies"]',
                'button:has-text("Permitir todos os cookies")',
                'button:has-text("Got it!")',
                'button:has-text("Aceitar")',
                'button:has-text("Accept All")',
                '[aria-label="Aceitar cookies"]',
                '#cookie-notice button',
                '.cookie-consent button',
                'button:has-text("Ok")',
                'button:has-text("Entendi")',
                '.cookies button',
                '#cookies button'
            ]
            
            for selector in cookie_button_selectors:
                try:
                    logger.info(f"Tentando clicar no botão de cookies com seletor: {selector}")
                    cookie_button = await self.page.wait_for_selector(selector, timeout=3000, state="visible")
                    if cookie_button:
                        # Tenta clicar usando diferentes estratégias
                        try:
                            await cookie_button.click()
                        except Exception as e:
                            logger.debug(f"Falha no clique direto: {str(e)}, tentando via JavaScript")
                            await self.page.evaluate("""(selector) => {
                                const button = document.querySelector(selector);
                                if (button) button.click();
                            }""", selector)
                        
                        logger.info("Popup de cookies fechado com sucesso")
                        await asyncio.sleep(1)  # Aguarda a animação do popup
                        break
                except Exception as e:
                    logger.debug(f"Falha ao tentar seletor {selector}: {str(e)}")
                    continue

            # Estratégias para encontrar e preencher o campo CPF (atualizado)
            cpf_strategies = [
                {
                    "type": "selector",
                    "selector": 'input#combo__input',
                    "timeout": 7000
                }
            ]
            
            # Encontra o campo CPF
            logger.info("Procurando campo de CPF...")
            cpf_element = None
            for strategy in cpf_strategies:
                try:
                    if strategy["type"] == "selector":
                        element = await self.page.wait_for_selector(
                            strategy["selector"],
                            timeout=strategy.get("timeout", 7000)
                        )
                        if element:
                            cpf_element = element
                            logger.info(f"Campo CPF encontrado via seletor: {strategy['selector']}")
                            break
                except Exception as e:
                    logger.debug(f"Falha na estratégia de busca do CPF: {str(e)}")
                    continue
            if not cpf_element:
                raise AutomationError("Não foi possível encontrar o campo de CPF")

            # Preenche o CPF número por número
            try:
                await cpf_element.fill("")
                await asyncio.sleep(0.5)
                cpf_digits = ''.join(filter(str.isdigit, cpf))
                logger.info(f"Iniciando preenchimento do CPF dígito por dígito...")
                for i, digit in enumerate(cpf_digits):
                    await cpf_element.type(digit)
                    await asyncio.sleep(0.2)
                    logger.info(f"Dígito {i+1}/11 inserido")
                final_value = await cpf_element.evaluate('(element) => element.value')
                if len(''.join(filter(str.isdigit, final_value))) == 11:
                    logger.info(f"CPF preenchido com sucesso. Valor final: {final_value}")
                else:
                    raise Exception(f"CPF não foi preenchido corretamente. Valor atual: {final_value}")
            except Exception as e:
                logger.error(f"Erro ao preencher CPF: {str(e)}")
                raise AutomationError(f"Falha ao preencher CPF: {str(e)}")

            # Aguarda atualização automática com lógica mais robusta
            logger.info("Aguardando carregamento da página após inserção do CPF...")
            
            # Estratégias para detectar se a página carregou adequadamente
            page_loaded = False
            max_wait_time = 30  # Aumenta para 30 segundos
            check_interval = 2   # Verifica a cada 2 segundos
            elapsed_time = 0
            
            while elapsed_time < max_wait_time and not page_loaded:
                try:
                    # Verifica se a URL mudou para /comparador (cliente elegível)
                    current_url = self.page.url
                    if "/comparador" in current_url:
                        logger.info("URL mudou para /comparador - cliente elegível detectado")
                        page_loaded = True
                        break
                    
                    # Verifica se há indicadores de carregamento na página
                    page_content = await self.page.content()
                    
                    # Verifica se há mensagens de "não elegível" no conteúdo
                    if ("não elegível" in page_content.lower() or 
                        "nao elegivel" in page_content.lower() or
                        "não é elegível" in page_content.lower() or
                        "nao e elegivel" in page_content.lower()):
                        logger.info("Mensagem de não elegível detectada no conteúdo da página")
                        page_loaded = True
                        break
                    
                    # Verifica se há elementos que indicam que a página carregou
                    # (como formulários de proposta, botões de ação, etc.)
                    loaded_indicators = [
                        'form[action*="proposta"]',
                        'button:has-text("Continuar")',
                        'button:has-text("Próximo")',
                        'button:has-text("Avançar")',
                        '.proposta-form',
                        '.elegibilidade-resultado',
                        '[data-testid*="elegibilidade"]',
                        '.loading',
                        '.spinner',
                        '.carregando'
                    ]
                    
                    # Se encontrar elementos de loading, aguarda mais
                    loading_elements = []
                    for indicator in loaded_indicators:
                        try:
                            element = await self.page.query_selector(indicator)
                            if element:
                                loading_elements.append(indicator)
                        except:
                            continue
                    
                    if loading_elements:
                        logger.info(f"Elementos de carregamento detectados: {loading_elements}. Aguardando...")
                        await asyncio.sleep(check_interval)
                        elapsed_time += check_interval
                        continue
                    
                    # Verifica se a página está "quieta" (sem mudanças por alguns segundos)
                    if elapsed_time > 10:  # Após 10 segundos, verifica se a página está estável
                        logger.info("Verificando se a página está estável...")
                        
                        # Aguarda um pouco mais para garantir que não há mais mudanças
                        await asyncio.sleep(3)
                        
                        # Verifica se a página está completamente carregada
                        if await self._is_page_fully_loaded():
                            logger.info("Página completamente carregada detectada")
                            page_loaded = True
                            break
                        else:
                            logger.info("Página ainda não está completamente carregada, aguardando mais...")
                    
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
                    
                except Exception as e:
                    logger.warning(f"Erro durante verificação de carregamento: {str(e)}")
                    await asyncio.sleep(check_interval)
                    elapsed_time += check_interval
            
            if not page_loaded:
                logger.warning(f"Timeout após {max_wait_time} segundos. Prosseguindo com verificação...")
            
            # Aguarda um pouco mais para garantir que tudo carregou
            logger.info("Aguardando 3 segundos finais para garantir carregamento completo...")
            await asyncio.sleep(3)
            
            # Verificação final antes de tirar o screenshot
            logger.info("Fazendo verificação final de carregamento...")
            if not await self._is_page_fully_loaded():
                logger.warning("Página ainda não está completamente carregada, mas prosseguindo com screenshot...")
                # Aguarda mais um pouco
                await asyncio.sleep(2)
            else:
                logger.info("Página confirmada como completamente carregada")
            
            # Tirar print após carregamento da página
            logger.info("Capturando screenshot da tela de resposta de elegibilidade...")
            screenshot_final = await self._capture_screenshot("resposta_elegibilidade")

            # Verificar elegibilidade com lógica mais robusta
            logger.info("Analisando resultado da elegibilidade...")
            url_atual = self.page.url
            page_content = await self.page.content()
            
            # Verifica múltiplos indicadores de elegibilidade
            elegivel_indicators = [
                "/comparador" in url_atual,
                "comparador" in page_content.lower(),
                "proposta" in page_content.lower() and "form" in page_content.lower(),
                "continuar" in page_content.lower() and "proposta" in page_content.lower(),
                "próximo" in page_content.lower() and "proposta" in page_content.lower()
            ]
            
            nao_elegivel_indicators = [
                "não elegível" in page_content.lower(),
                "nao elegivel" in page_content.lower(),
                "não é elegível" in page_content.lower(),
                "nao e elegivel" in page_content.lower(),
                "não possui elegibilidade" in page_content.lower(),
                "nao possui elegibilidade" in page_content.lower(),
                "não atende aos critérios" in page_content.lower(),
                "nao atende aos criterios" in page_content.lower()
            ]
            
            if any(elegivel_indicators):
                result_text = "Cliente elegível"
                logger.info("Cliente elegível detectado através de múltiplos indicadores")
            elif any(nao_elegivel_indicators):
                result_text = "Cliente não elegível"
                logger.info("Cliente não elegível detectado através de mensagens na página")
            else:
                # Verifica se há elementos visuais que indicam carregamento incompleto
                loading_elements = await self.page.query_selector_all('.loading, .spinner, .carregando, [data-loading="true"]')
                if loading_elements:
                    result_text = "Resultado Indeterminado - Página ainda carregando"
                    logger.warning("Página ainda apresenta elementos de carregamento")
                else:
                    result_text = "Resultado Indeterminado - Verificar manualmente"
                    logger.warning("Não foi possível determinar elegibilidade automaticamente")
            
            logger.info(f"Resultado final: {result_text}")

            # Retorna o print mais importante (após atualização)
            return result_text.strip(), f"Verificação concluída: {result_text.strip()}", screenshot_final

        except Exception as e:
            logger.error(f"Erro durante verificação: {str(e)}")
            if not screenshot_base64:
                logger.info("Tentando capturar screenshot de erro...")
                screenshot_base64 = await self._capture_screenshot("erro_verificacao")
            raise AutomationError(f"Falha na verificação: {str(e)}")

    async def _is_page_fully_loaded(self) -> bool:
        """
        Verifica se a página está completamente carregada
        """
        try:
            # Verifica se não há elementos de loading visíveis
            loading_selectors = [
                '.loading',
                '.spinner', 
                '.carregando',
                '[data-loading="true"]',
                '.loading-spinner',
                '.ajax-loader',
                '.progress-bar'
            ]
            
            for selector in loading_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible():
                        logger.debug(f"Elemento de loading encontrado: {selector}")
                        return False
                except:
                    continue
            
            # Verifica se a página está "quieta" (sem mudanças recentes)
            try:
                await self.page.wait_for_load_state("networkidle", timeout=2000)
                return True
            except:
                # Se não conseguir aguardar networkidle, verifica outros indicadores
                pass
            
            # Verifica se há conteúdo significativo na página
            page_content = await self.page.content()
            if len(page_content) < 1000:  # Página muito pequena pode indicar carregamento incompleto
                logger.debug("Página com conteúdo muito pequeno, possivelmente ainda carregando")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Erro ao verificar se página está carregada: {str(e)}")
            return False

    async def _capture_screenshot(self, prefix: str) -> Optional[str]:
        """
        Captura screenshot da página atual e retorna como base64
        """
        try:
            logger.info(f"Iniciando captura do screenshot ({prefix})...")
            screenshot_bytes = await self.page.screenshot(
                full_page=True,
                type='jpeg',
                quality=80
            )
            import base64
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            logger.info(f"Screenshot capturado com sucesso ({prefix}). Tamanho: {len(screenshot_base64)} caracteres")
            return screenshot_base64
        except Exception as e:
            logger.error(f"Erro ao capturar screenshot: {str(e)}")
            return None

async def run_automation(run_id: str, login: str, senha: str, cpf: str) -> Dict[str, str]:
    """
    Função principal que executa todo o fluxo de automação
    """
    resource_manager = ResourceManager()
    
    # Tenta adquirir uma vaga para executar
    while not await resource_manager.acquire_instance(run_id):
        await asyncio.sleep(5)  # Espera 5 segundos antes de tentar novamente
    
    try:
        log_summary = []
        start_time = time.time()
        screenshot = None
        
        async with PanAutomation(login_url="https://veiculos.bancopan.com.br/login") as automation:
            log_summary.append("Iniciando automação")
            
            await automation.initialize()
            log_summary.append("Navegador inicializado")
            
            await automation.login(login, senha)
            log_summary.append("Login realizado com sucesso")
            
            result, verification_log, screenshot = await automation.verificar_elegibilidade(cpf)
            log_summary.append(verification_log)
            
            if screenshot:
                logger.info("Screenshot capturado com sucesso e pronto para retorno")
            else:
                logger.warning("Nenhum screenshot disponível para retorno")
            
            execution_time = time.time() - start_time
            log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
            
            return {
                "result": result,
                "log_summary": "\n".join(log_summary),
                "screenshot": screenshot
            }
    finally:
        # Sempre libera a instância, mesmo em caso de erro
        resource_manager.release_instance(run_id) 
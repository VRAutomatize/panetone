import asyncio
import logging
from typing import Dict, Tuple, Optional, List
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

    @retry_on_failure(max_retries=3, delay=2)
    async def verificar_elegibilidade(self, cpf: str) -> Tuple[str, str, Optional[str]]:
        """
        Verifica a elegibilidade do cliente usando o CPF
        Retorna uma tupla com (resultado, log_summary, screenshot_base64)
        """
        try:
            logger.info("Iniciando verificação de elegibilidade...")
            current_url = self.page.url
            logger.info(f"URL atual antes da verificação: {current_url}")

            # Lista de possíveis seletores para o campo de CPF
            cpf_selectors = [
                'input[formcontrolname="cpf"]',
                'input[name="cpf"]',
                'input[placeholder="000.000.000-00"]'
            ]

            # Aguarda e preenche o campo de CPF
            logger.info("Procurando campo de CPF...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar campo de CPF...")
                    
                    # Aguarda explicitamente o campo aparecer
                    await self.page.wait_for_selector('input[formcontrolname="cpf"]', timeout=5000)
                    
                    # Tenta preencher usando JavaScript primeiro
                    try:
                        await self.page.evaluate('''(cpf) => {
                            const input = document.querySelector('input[formcontrolname="cpf"]');
                            if (input) {
                                input.value = cpf;
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                                input.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }''', cpf)
                        logger.info("CPF preenchido via JavaScript")
                        break
                    except Exception as e:
                        logger.warning(f"Falha ao preencher CPF via JavaScript: {str(e)}")
                    
                    # Se falhar, tenta o método tradicional
                    cpf_field = await self._try_selectors(cpf_selectors)
                    
                    if not cpf_field:
                        raise TimeoutError("Campo de CPF não encontrado com nenhum seletor")
                    
                    # Tenta preencher usando diferentes estratégias
                    if await self._try_fill_input(cpf_field, cpf, is_cpf=True):
                        logger.info("Campo de CPF localizado e preenchido com sucesso")
                        break
                    else:
                        raise TimeoutError("Não foi possível preencher o campo de CPF")
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de localizar campo de CPF...")
                    if attempt == 1:
                        logger.info("Tentando recarregar a página...")
                        await self.page.reload(wait_until='domcontentloaded')
                        await asyncio.sleep(1)
                    else:
                        await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao preencher campo de CPF após várias tentativas")

            # Lista de possíveis seletores para o botão de avançar
            button_selectors = [
                'button[type="submit"]',
                'button.pan-mahoe-button',
                'button:has-text("Avançar")',
                'button:has-text("Continuar")',
                'button:has-text("Próximo")',
                'button.next-button',
                'button[formcontrolname="submit"]',
                'span.pan-mahoe-button__wrapper',
                '.pan-mahoe-button__wrapper',
                'button.pan-mahoe-button__wrapper',
                'div.mahoe-ripple'
            ]

            # Clica no botão de avançar
            logger.info("Procurando botão de avançar...")
            for attempt in range(3):
                try:
                    logger.info(f"Tentativa {attempt + 1} de localizar botão de avançar...")
                    next_button = await self._try_selectors(button_selectors)
                    
                    if not next_button:
                        raise TimeoutError("Botão de avançar não encontrado com nenhum seletor")
                    
                    # Tenta clicar usando diferentes estratégias
                    if await self._try_click_button(next_button):
                        logger.info("Botão de avançar localizado e clicado com sucesso")
                        break
                    else:
                        raise TimeoutError("Não foi possível clicar no botão de avançar")
                except TimeoutError:
                    logger.warning(f"Timeout na tentativa {attempt + 1} de localizar botão de avançar...")
                    if attempt == 1:
                        logger.info("Tentando recarregar a página...")
                        await self.page.reload(wait_until='domcontentloaded')
                        await asyncio.sleep(1)
                    else:
                        await asyncio.sleep(1)
            else:
                raise AutomationError("Falha ao clicar no botão de avançar após várias tentativas")

            # Aguarda o resultado aparecer
            logger.info("Aguardando resultado da verificação...")
            
            # Lista de possíveis seletores para mensagens de resultado
            result_selectors = [
                'text="Cliente Elegível"',
                'text="Cliente Não Elegível"',
                '*:has-text("Cliente Elegível")',
                '*:has-text("Cliente Não Elegível")',
                '.resultado-elegibilidade',
                '.mensagem-resultado'
            ]

            try:
                # Aguarda um tempo para garantir que a página carregou completamente
                await asyncio.sleep(2)
                
                # Captura o estado atual da página
                logger.info("Verificando estado atual da página...")
                current_url = self.page.url
                logger.info(f"URL após submissão do CPF: {current_url}")
                
                page_content = await self.page.content()
                if "erro" in page_content.lower() or "error" in page_content.lower():
                    logger.warning("Detectada possível mensagem de erro na página")
                
                # Tenta encontrar qualquer mensagem de resultado
                for selector in result_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=5000)
                        if element:
                            result_text = await element.text_content()
                            logger.info(f"Texto encontrado com seletor {selector}: {result_text}")
                            screenshot_base64 = await self._capture_screenshot("resultado_elegibilidade")
                            return result_text.strip(), f"Cliente verificado como {result_text.strip().lower()}", screenshot_base64
                    except Exception as e:
                        logger.debug(f"Seletor {selector} não encontrou resultado: {str(e)}")
                
                # Se não encontrou resultado específico, vamos capturar mais informações
                logger.warning("Nenhum resultado específico encontrado, coletando informações adicionais...")
                
                # Tenta encontrar qualquer mensagem ou texto relevante
                try:
                    # Procura por textos que possam indicar o status
                    texts = await self.page.evaluate('''() => {
                        const elements = document.querySelectorAll('*');
                        return Array.from(elements)
                            .map(el => el.textContent)
                            .filter(text => text && text.trim())
                            .filter(text => 
                                text.toLowerCase().includes('elegível') ||
                                text.toLowerCase().includes('elegivel') ||
                                text.toLowerCase().includes('status') ||
                                text.toLowerCase().includes('resultado') ||
                                text.toLowerCase().includes('erro') ||
                                text.toLowerCase().includes('aguarde')
                            );
                    }''')
                    
                    if texts:
                        logger.info("Textos relevantes encontrados na página:")
                        for text in texts:
                            logger.info(f"- {text.strip()}")
                except Exception as e:
                    logger.error(f"Erro ao buscar textos na página: {str(e)}")

                # Captura screenshot em caso de falha
                screenshot_base64 = await self._capture_screenshot("verificacao_falha")
                
                return "Resultado Indeterminado", "Não foi possível determinar a elegibilidade do cliente. Verifique o screenshot para mais detalhes.", screenshot_base64

            except TimeoutError:
                logger.warning("Timeout ao aguardar resultado da verificação")
                screenshot_base64 = await self._capture_screenshot("timeout_verificacao")
                return "Timeout", "Timeout ao aguardar resultado da verificação. Verifique o screenshot para mais detalhes.", screenshot_base64

        except TimeoutError as e:
            logger.error(f"Timeout durante verificação de elegibilidade: {str(e)}")
            screenshot_base64 = await self._capture_screenshot("erro_verificacao")
            raise AutomationError("Timeout ao tentar verificar elegibilidade")
        except Exception as e:
            logger.error(f"Erro durante verificação de elegibilidade: {str(e)}")
            screenshot_base64 = await self._capture_screenshot("erro_verificacao")
            raise AutomationError(f"Falha na verificação: {str(e)}")

    async def _capture_screenshot(self, prefix: str) -> str:
        """
        Captura screenshot da página atual e retorna como base64
        """
        try:
            logger.info(f"Capturando screenshot ({prefix})...")
            screenshot_bytes = await self.page.screenshot(
                full_page=True,
                type='jpeg',
                quality=80
            )
            import base64
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            logger.info(f"Screenshot capturado com sucesso ({prefix})")
            return screenshot_base64
        except Exception as e:
            logger.error(f"Erro ao capturar screenshot: {str(e)}")
            return None

async def run_automation(run_id: str, login: str, senha: str, cpf: str) -> Dict[str, str]:
    """
    Função principal que executa todo o fluxo de automação
    """
    log_summary = []
    start_time = time.time()
    screenshot = None
    
    try:
        async with PanAutomation(login_url="https://veiculos.bancopan.com.br/login") as automation:
            log_summary.append("Iniciando automação")
            
            await automation.initialize()
            log_summary.append("Navegador inicializado")
            
            await automation.login(login, senha)
            log_summary.append("Login realizado com sucesso")
            
            result, verification_log, screenshot = await automation.verificar_elegibilidade(cpf)
            log_summary.append(verification_log)
            
            execution_time = time.time() - start_time
            log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
            
            return {
                "result": result,
                "log_summary": "\n".join(log_summary),
                "screenshot": screenshot
            }
            
    except AutomationError as e:
        log_summary.append(f"Erro na automação: {str(e)}")
        execution_time = time.time() - start_time
        log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary),
            "screenshot": screenshot
        }
    except Exception as e:
        log_summary.append(f"Erro inesperado: {str(e)}")
        execution_time = time.time() - start_time
        log_summary.append(f"Tempo total de execução: {execution_time:.2f} segundos")
        return {
            "result": f"Erro: {str(e)}",
            "log_summary": "\n".join(log_summary),
            "screenshot": screenshot
        } 
import time
import os
import traceback
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class SunatSession:
    _driver = None

    def __init__(self):
        self.ruc = os.getenv("SUNAT_RUC")
        self.user = os.getenv("SUNAT_USER")
        self.password = os.getenv("SUNAT_PASS")
        self.env = os.getenv("ENVIRONMENT", "LOCAL")
        
        missing = []
        if not self.ruc:
            missing.append("SUNAT_RUC")
        if not self.user:
            missing.append("SUNAT_USER")
        if not self.password:
            missing.append("SUNAT_PASS")
            
        if missing:
            print(f"❌ Faltan variables: {', '.join(missing)}")
        else:
            print(f"✅ Credenciales cargadas - RUC: {self.ruc[:4]}***{self.ruc[-3:]}")
            print(f"🌍 Entorno: {self.env}")

    def login_and_get_cookies(self):
        try:
            if not all([self.ruc, self.user, self.password]):
                raise Exception("Credenciales incompletas")
                
            if SunatSession._driver is None:
                self._iniciar_y_loguear()
            
            if SunatSession._driver is None:
                raise Exception("No se pudo inicializar el driver")
                
            driver = SunatSession._driver
            
            try:
                driver.current_url
            except:
                print("⚠️ Driver no responde, reiniciando...")
                SunatSession._driver = None
                self._iniciar_y_loguear()
                driver = SunatSession._driver
            
            selenium_cookies = driver.get_cookies()
            user_agent = driver.execute_script("return navigator.userAgent")
            
            if not selenium_cookies:
                raise Exception("No se obtuvieron cookies")
            
            cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in selenium_cookies])
            
            print(f"✅ Sesión obtenida - Cookies: {len(selenium_cookies)}")
            
            return {
                "cookies": cookie_string,
                "user_agent": user_agent
            }
            
        except Exception as e:
            print(f"❌ Error en login: {e}")
            traceback.print_exc()
            if SunatSession._driver:
                try:
                    SunatSession._driver.quit()
                except:
                    pass
                SunatSession._driver = None
            return None

    def _iniciar_y_loguear(self):
        try:
            ENVIRONMENT = os.getenv('ENVIRONMENT', 'LOCAL')
            print(f"🚀 Iniciando navegador en modo {ENVIRONMENT}...")
            
            if ENVIRONMENT == "LOCAL":
                from selenium.webdriver.edge.options import Options as EdgeOptions
                options = EdgeOptions()
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_argument('--no-sandbox')
                options.add_argument('--start-maximized')
                options.add_argument("--headless=new") 
                options.add_argument("--disable-gpu")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0")
                
                SunatSession._driver = webdriver.Edge(options=options)
                print("   ✅ Edge iniciado (modo local)")
                
            else:
                from selenium.webdriver.chrome.options import Options as ChromeOptions
                from selenium.webdriver.chrome.service import Service
                
                # Verificar que los binarios existen
                chrome_path = "/usr/bin/google-chrome"
                chromedriver_path = "/usr/local/bin/chromedriver"
                
                if not os.path.exists(chrome_path):
                    print(f"   ❌ Chrome no encontrado en {chrome_path}")
                    raise Exception(f"Chrome binary not found at {chrome_path}")
                
                if not os.path.exists(chromedriver_path):
                    print(f"   ❌ ChromeDriver no encontrado en {chromedriver_path}")
                    raise Exception(f"ChromeDriver not found at {chromedriver_path}")
                
                print(f"   Chrome encontrado en: {chrome_path}")
                print(f"   ChromeDriver encontrado en: {chromedriver_path}")
                
                options = ChromeOptions()
                options.binary_location = chrome_path
                
                options.add_argument("--headless=new")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                
                service = Service(chromedriver_path)
                SunatSession._driver = webdriver.Chrome(service=service, options=options)
                print("   ✅ Chrome Headless iniciado (modo producción)")
            
            driver = SunatSession._driver
            wait = WebDriverWait(driver, 20)
            
            print("🔐 Accediendo al portal SUNAT...")
            driver.get("https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm")
            
            print("⌨️ Ingresando credenciales...")
            ruc_field = wait.until(EC.presence_of_element_located((By.ID, "txtRuc")))
            ruc_field.send_keys(self.ruc)
            driver.find_element(By.ID, "txtUsuario").send_keys(self.user)
            driver.find_element(By.ID, "txtContrasena").send_keys(self.password)
            
            btn_aceptar = driver.find_element(By.ID, "btnAceptar")
            driver.execute_script("arguments[0].click();", btn_aceptar)
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "divMenu0")))
                print("✅ Menú principal cargado")
            except:
                print("⚠️ Menú tardó, continuando...")
            
            print("🔄 Navegando a Consulta Unificada...")
            time.sleep(3)
            driver.get("https://ww1.sunat.gob.pe/ol-ti-itconsultaunificada/consultaUnificada/index")
            
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(2)
            
            print("✅ Sesión iniciada correctamente")
            
        except Exception as e:
            print(f"❌ Error en _iniciar_y_loguear: {str(e)}")
            traceback.print_exc()
            if SunatSession._driver:
                try:
                    SunatSession._driver.quit()
                except:
                    pass
                SunatSession._driver = None
            raise

    def quit(self):
        if SunatSession._driver:
            try:
                SunatSession._driver.quit()
                SunatSession._driver = None
                print("✅ Driver cerrado")
            except:
                pass

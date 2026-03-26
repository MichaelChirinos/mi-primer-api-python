import time
import os
import traceback
from requests import options
from requests import options
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class SunatSession:
    _driver = None

    def __init__(self):
        self.ruc = os.getenv("SUNAT_RUC")
        self.user = os.getenv("SUNAT_USER")
        self.password = os.getenv("SUNAT_PASS")
        
        missing = []
        if not self.ruc:
            missing.append("SUNAT_RUC")
        if not self.user:
            missing.append("SUNAT_USER")
        if not self.password:
            missing.append("SUNAT_PASS")
            
        if missing:
            print(f"Error: Faltan las siguientes variables de entorno: {', '.join(missing)}")
        else:
            print("Credenciales cargadas correctamente")
            print(f"   RUC: {self.ruc[:4]}***{self.ruc[-3:]}")
            print(f"   Usuario: {self.user}")

    def login_and_get_cookies(self):
        try:
            if not all([self.ruc, self.user, self.password]):
                raise Exception("Credenciales de SUNAT incompletas.")
                
            if SunatSession._driver is None:
                self._iniciar_y_loguear()
            
            if SunatSession._driver is None:
                raise Exception("No se pudo inicializar el driver")
                
            driver = SunatSession._driver
            
            # Verificar que el driver sigue vivo
            try:
                driver.current_url
            except:
                print("Driver no responde, reiniciando")
                SunatSession._driver = None
                self._iniciar_y_loguear()
                driver = SunatSession._driver
            
            selenium_cookies = driver.get_cookies()
            user_agent = driver.execute_script("return navigator.userAgent")
            
            if not selenium_cookies:
                raise Exception("No se obtuvieron cookies del navegador")
            
            cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in selenium_cookies])
            
            print(f"Datos de sesión extraídos correctamente. Cookies: {len(selenium_cookies)}")
            
            return {
                "cookies": cookie_string,
                "user_agent": user_agent
            }
        except Exception as e:
            print(f"❌ Error crítico obteniendo sesión: {e}")
            print(traceback.format_exc())
            if SunatSession._driver:
                try:
                    SunatSession._driver.quit()
                except:
                    pass
                SunatSession._driver = None
            return None

    def _iniciar_y_loguear(self):        
        try:
            options = Options()
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--no-sandbox')
            options.add_argument('--start-maximized')
            options.add_argument("--headless=new") 
            options.add_argument("--disable-gpu")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0")

            SunatSession._driver = webdriver.Edge(options=options)
            driver = SunatSession._driver
            wait = WebDriverWait(driver, 15) 
            
            driver.get("https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm")
            
            print("⌨Ingresando credenciales")
            ruc_field = wait.until(EC.presence_of_element_located((By.ID, "txtRuc")))
            ruc_field.send_keys(self.ruc)
            driver.find_element(By.ID, "txtUsuario").send_keys(self.user)
            driver.find_element(By.ID, "txtContrasena").send_keys(self.password)
            
            btn_aceptar = driver.find_element(By.ID, "btnAceptar")
            driver.execute_script("arguments[0].click();", btn_aceptar)
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "divMenu0")))
                print("✅ Menú cargado visualmente.")
            except Exception:
                print("El menú visual tardó mucho. Intentando forzar sincronización")
                
            print("Sincronizando módulo de Consultas")
            url_modulo = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm?pestana=*&agrupacion=*&exe=11.5.10.1.1"
            driver.get(url_modulo)
            time.sleep(6)

            print("Saltando a Consulta Unificada")
            driver.get("https://ww1.sunat.gob.pe/ol-ti-itconsultaunificada/consultaUnificada/index")
            
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            print("Proceso de sesión completado.")
            
        except Exception as e:
            print(f"Error crítico en _iniciar_y_loguear: {str(e)}")
            if SunatSession._driver:
                try: SunatSession._driver.quit()
                except: pass
                SunatSession._driver = None
            raise

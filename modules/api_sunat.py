
import requests
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SunatAPI:
    def __init__(self, cookies_string, user_agent):
        self.url_base = "https://ww1.sunat.gob.pe/ol-ti-itconsultaunificada/consultaUnificada"
        self.headers = {
            'User-Agent': user_agent,
            'Referer': f'{self.url_base}/index',
            'Origin': 'https://ww1.sunat.gob.pe',
            'Cookie': cookies_string,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'es-ES,es;q=0.9',
            'Connection': 'keep-alive'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def consultar_individual(self, datos):
        url = f"{self.url_base}/consultaIndividual"
        try:
            logger.info(f"Consultando comprobante: {datos.get('numeroSerie')}-{datos.get('numero')}")
            
            headers_temp = self.headers.copy()
            headers_temp['Content-Type'] = 'application/x-www-form-urlencoded'
            
            response = self.session.post(url, data=datos, headers=headers_temp, timeout=15)
            
            if response.status_code == 200:
                return self._procesar_respuesta_sunat(response.text)
            else:
                return {"rpta": 0, "error": f"Error HTTP {response.status_code}"}
            
        except Exception as e:
            logger.error(f"Error en consulta individual: {e}")
            return {"error": str(e), "rpta": 0}

    def consultar_masivo(self, contenido_txt):
        url = f"{self.url_base}/importarFromTXT"
        try:
            payload = {
                'archivoContenido': contenido_txt.strip(), 
                'token': ''
            }
        
            headers_envio = self.headers.copy()
            headers_envio['Content-Type'] = 'application/x-www-form-urlencoded'
            
            print(f"Enviando {len(contenido_txt.splitlines())} líneas a SUNAT")
            
            response = self.session.post(
                url, 
                data=payload, 
                headers=headers_envio, 
                timeout=30
            )
            
            print(f"Respuesta RAW de SUNAT: {response.text}")
            
            return self._procesar_respuesta_sunat(response.text)
            
        except Exception as e:
            print(f"Error en consulta masiva: {e}")
            return {"error": str(e), "rpta": 0}
        
        
    def _procesar_respuesta_sunat(self, texto_respuesta):
        try:
            if texto_respuesta.startswith('"') and texto_respuesta.endswith('"'):
                texto_respuesta = texto_respuesta[1:-1].replace('\\"', '"')
            
            data = json.loads(texto_respuesta)
            
            if isinstance(data, str):
                data = json.loads(data)

            map_estado_cp = {"1": "ACEPTADO", "2": "ANULADO", "3": "NO EXISTE"}
            map_estado_ruc = {"00": "ACTIVO", "01": "BAJA PROVISIONAL", "02": "BAJA DEFINITIVA"}
            map_cond_dom = {"00": "HABIDO", "09": "PENDIENTE", "12": "NO HABIDO"}

            if 'lista' in data:
                resultados_limpios = []
                for item in data['lista']:
                    obs = " ".join(item.get('observaciones', [])).replace("- ", "").strip()
                    
                    resultados_limpios.append({
                        "ruc_emisor": item.get('numRuc'),
                        "comprobante": f"{item.get('numeroSerie')}-{item.get('numero')}",
                        "fecha": item.get('fechaEmision'),
                        "monto": item.get('monto'),
                        "estado_cp": map_estado_cp.get(item.get('estadoCp'), "DESCONOCIDO"),
                        "estado_ruc": map_estado_ruc.get(item.get('estadoRuc'), "OTROS"),
                        "condicion_domicilio": map_cond_dom.get(item.get('condDomiRuc'), "OTROS"),
                        "mensaje": obs if obs else "Sin observaciones"
                    })
                
                return {
                    "rpta": 1,
                    "total": len(resultados_limpios),
                    "data": resultados_limpios
                }
            
            return data

        except Exception as e:
            print(f"Error procesando: {e}")
            return {"rpta": 0, "error": "Error de formato en respuesta SUNAT", "raw": texto_respuesta[:100]}


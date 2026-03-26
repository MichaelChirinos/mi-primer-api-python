from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os
import tempfile
from werkzeug.utils import secure_filename
import traceback
import fitz  # PyMuPDF
from datetime import datetime
import json
import re
import threading
import time

# Importar módulos SUNAT
from modules.sunat_session import SunatSession
from modules.sunat_api import SunatAPI

app = Flask(__name__)
CORS(app)

# ============================================
# CONFIGURACIÓN GROQ
# ============================================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
if not GROQ_API_KEY:
    print("ERROR: GROQ_API_KEY no está configurada")
else:
    print(f"GROQ_API_KEY configurada")

client = Groq(api_key=GROQ_API_KEY)

ALLOWED_EXTENSIONS = {'pdf', 'xml'}
MAX_FILE_SIZE = 10 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================
# GESTIÓN DE SESIÓN SUNAT
# ============================================
session_manager = {
    "cookies": None,
    "user_agent": None,
    "status": "initializing",
    "last_update": None,
    "error_msg": None
}

def obtener_sesion_sunat():
    global session_manager
    if session_manager["status"] == "ready" and session_manager["cookies"]:
        return session_manager
    
    print("🔄 Renovando sesión SUNAT...")
    session_manager["status"] = "authenticating"
    
    try:
        bot = SunatSession()
        data = bot.login_and_get_cookies()
        
        if data and data.get("cookies"):
            session_manager["cookies"] = data["cookies"]
            session_manager["user_agent"] = data["user_agent"]
            session_manager["status"] = "ready"
            session_manager["last_update"] = datetime.now().strftime("%H:%M:%S")
            session_manager["error_msg"] = None
            print(f"✅ Sesión SUNAT renovada a las {session_manager['last_update']}")
        else:
            raise Exception("No se obtuvieron cookies")
            
    except Exception as e:
        session_manager["status"] = "error"
        session_manager["error_msg"] = str(e)
        print(f"❌ Error: {e}")
    
    return session_manager

def background_auth_worker():
    while True:
        time.sleep(900)  # 15 minutos
        obtener_sesion_sunat()

auth_thread = threading.Thread(target=background_auth_worker, daemon=True)
auth_thread.start()
obtener_sesion_sunat()

# ============================================
# FUNCIÓN AUXILIAR PARA SUNAT MASIVO
# ============================================
def transformar_formato_sunat(contenido_original):
    lineas_transformadas = []
    lineas = contenido_original.replace('\r\n', '\n').strip().split('\n')
    
    for linea in lineas:
        if not linea.strip():
            continue
        campos = linea.split('|')
        if len(campos) != 6:
            continue
        
        numRuc, codComp, numeroSerie, numero, fechaEmision, monto = [c.strip() for c in campos]
        linea_sunat = f"{numero}|{numeroSerie}|{codComp}|{fechaEmision}|{numRuc}|||{monto}"
        lineas_transformadas.append(linea_sunat)
    
    return '\r\n'.join(lineas_transformadas) + '\r\n'

# ============================================
# ENDPOINT 1: COMPARAR PDF vs XML + EXTRACCIÓN
# ============================================
@app.route('/comparar', methods=['POST'])
def comparar():
    print("\n=== NUEVA PETICIÓN A /comparar ===")
    
    temp_paths = []
    try:
        # Verificar archivos
        if 'pdf' not in request.files:
            return jsonify({'error': 'No se encontró el archivo PDF'}), 400
        if 'xml' not in request.files:
            return jsonify({'error': 'No se encontró el archivo XML'}), 400
        
        pdf_file = request.files['pdf']
        xml_file = request.files['xml']
        
        print(f"PDF recibido: {pdf_file.filename}")
        print(f"XML recibido: {xml_file.filename}")
        
        # Validar extensiones
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'El primer archivo debe ser PDF'}), 400
        if not xml_file.filename.lower().endswith('.xml'):
            return jsonify({'error': 'El segundo archivo debe ser XML'}), 400
        
        # Leer contenidos
        pdf_content = pdf_file.read()
        xml_content = xml_file.read()
        
        # Guardar temporales
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp:
            tmp.write(pdf_content)
            pdf_path = tmp.name
            temp_paths.append(pdf_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml', mode='wb') as tmp:
            tmp.write(xml_content)
            xml_path = tmp.name
            temp_paths.append(xml_path)
        
        # Extraer texto
        print("\nExtrayendo texto...")
        pdf_text = ""
        doc = fitz.open(pdf_path)
        for page in doc:
            pdf_text += page.get_text()
        doc.close()
        
        xml_text = ""
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_text = f.read()
        
        print(f"PDF: {len(pdf_text)} caracteres")
        print(f"XML: {len(xml_text)} caracteres")
        
        # Limitar textos
        pdf_limitado = pdf_text[:20000]
        xml_limitado = xml_text[:20000]
        
        # ============================================
        # PROMPT: Comparación + Extracción de datos
        # ============================================
        prompt_unificado = f"""
        Eres un auditor de facturación electrónica peruana.

        **ARCHIVOS**
        - PDF: {pdf_file.filename}
        - XML: {xml_file.filename}

        **CONTENIDO PDF** (primeros 20000 caracteres):
        {pdf_limitado}

        **CONTENIDO XML** (primeros 20000 caracteres):
        {xml_limitado}

        Realiza DOS tareas y responde EXACTAMENTE con este formato:

        ===ANALISIS===
        [Aquí tu análisis en markdown]

        ===DATOS_SUNAT===
        {{
            "numRuc": "RUC del emisor",
            "codComp": "01",
            "numeroSerie": "SOLO LA SERIE (ejemplo: FF01, F001, B001)",
            "numero": "SOLO EL NÚMERO (ejemplo: 17763, sin la serie)",
            "fechaEmision": "DD/MM/YYYY",
            "monto": "Monto total",
            "tiene_discrepancias": true/false
        }}

        **REGLAS IMPORTANTES:**
        1. En el análisis, compara línea por línea ambos archivos
        2. Lista campos que coinciden y discrepancias
        3. Da veredicto final: APROBADA/REVISAR/RECHAZADA
        4. En DATOS_SUNAT, extrae los datos del XML (prioridad)
        5. numeroSerie y numero deben ir SEPARADOS
        6. Si el comprobante es "FF01-17763" → serie="FF01", numero="17763"
        7. NO incluyas el guión en el campo numero
        8. Si algún dato no existe, pon "NO_ENCONTRADO"
        9. "tiene_discrepancias" debe ser TRUE si hay alguna diferencia, FALSE si todo coincide
        """
        
        print("\n🤖 Llamando a Groq...")
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un auditor experto. Responde EXACTAMENTE con el formato solicitado."},
                {"role": "user", "content": prompt_unificado}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=5000
        )
        
        respuesta = completion.choices[0].message.content
        
        # Extraer análisis y datos
        resultado_analisis = respuesta
        datos_extraidos = None
        tiene_discrepancias = True
        
        if '===DATOS_SUNAT===' in respuesta:
            partes = respuesta.split('===DATOS_SUNAT===')
            resultado_analisis = partes[0].replace('===ANALISIS===', '').strip()
            
            json_texto = partes[1].strip()
            try:
                json_match = re.search(r'\{.*\}', json_texto, re.DOTALL)
                if json_match:
                    datos_extraidos = json.loads(json_match.group())
                    tiene_discrepancias = datos_extraidos.get('tiene_discrepancias', True)
                    print(f"✅ Datos extraídos: {datos_extraidos}")
            except Exception as e:
                print(f"Error parseando JSON: {e}")
                datos_extraidos = {
                    "numRuc": "ERROR_PARSEO",
                    "codComp": "ERROR_PARSEO",
                    "numeroSerie": "ERROR_PARSEO",
                    "numero": "ERROR_PARSEO",
                    "fechaEmision": "ERROR_PARSEO",
                    "monto": "ERROR_PARSEO"
                }
        
        return jsonify({
            'resultado': resultado_analisis,
            'pdf': pdf_file.filename,
            'xml': xml_file.filename,
            'fecha': datetime.now().isoformat(),
            'tiene_discrepancias': tiene_discrepancias,
            'datos_extraidos': datos_extraidos if datos_extraidos else {
                "numRuc": "NO_EXTRAIDO",
                "codComp": "NO_EXTRAIDO",
                "numeroSerie": "NO_EXTRAIDO",
                "numero": "NO_EXTRAIDO",
                "fechaEmision": "NO_EXTRAIDO",
                "monto": "NO_EXTRAIDO"
            }
        })
        
    except Exception as e:
        print(f"ERROR: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        for path in temp_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

# ============================================
# ENDPOINT 2: SUNAT - CONSULTA INDIVIDUAL
# ============================================
@app.route('/sunat/individual', methods=['POST'])
def sunat_individual():
    try:
        sesion = obtener_sesion_sunat()
        
        if sesion["status"] != "ready":
            return jsonify({"rpta": 0, "error": f"Sesión no lista: {sesion['status']}"}), 503

        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos", "rpta": 0}), 400
        
        campos_requeridos = ['numRuc', 'codComp', 'numeroSerie', 'numero', 'fechaEmision', 'monto']
        campos_faltantes = [c for c in campos_requeridos if c not in data]
        
        if campos_faltantes:
            return jsonify({"error": f"Faltan campos: {campos_faltantes}", "rpta": 0}), 400
        
        print(f"🔍 Consultando SUNAT: {data['numeroSerie']}-{data['numero']}")
        
        api = SunatAPI(sesion["cookies"], sesion["user_agent"])
        resultado = api.consultar_individual(data)
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"Error: {traceback.format_exc()}")
        return jsonify({"error": str(e), "rpta": 0}), 500

# ============================================
# ENDPOINT 3: SUNAT - CONSULTA MASIVA
# ============================================
@app.route('/sunat/masivo', methods=['POST'])
def sunat_masivo():
    try:
        sesion = obtener_sesion_sunat()
        
        if sesion["status"] != "ready":
            return jsonify({
                "rpta": 0,
                "error": f"Sesión no lista: {sesion['status']}"
            }), 503

        contenido_original = None
        
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                contenido_original = file.read().decode('utf-8')
        
        if not contenido_original and request.json:
            contenido_original = request.json.get('archivoContenido')

        if not contenido_original:
            return jsonify({"error": "No hay contenido", "rpta": 0}), 400

        contenido_sunat = transformar_formato_sunat(contenido_original)
        
        api = SunatAPI(sesion["cookies"], sesion["user_agent"])
        resultado = api.consultar_masivo(contenido_sunat)
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"Error: {traceback.format_exc()}")
        return jsonify({"error": str(e), "rpta": 0}), 500

# ============================================
# ENDPOINT 4: SUNAT - ESTADO DE SESIÓN
# ============================================
@app.route('/sunat/status', methods=['GET'])
def sunat_status():
    return jsonify(session_manager)

# ============================================
# ENDPOINT 5: PÁGINA PRINCIPAL
# ============================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'api': 'Factura Validator',
        'version': '2.0.0',
        'endpoints': {
            'comparar': 'POST /comparar (requiere pdf + xml)',
            'sunat_individual': 'POST /sunat/individual',
            'sunat_masivo': 'POST /sunat/masivo',
            'sunat_status': 'GET /sunat/status'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    env = os.environ.get('ENVIRONMENT', 'LOCAL')
    
    print("\n" + "="*60)
    print("🚀 FACTURA VALIDATOR API - UNIFICADA")
    print(f"🌍 Entorno: {env}")
    print(f"📡 Puerto: {port}")
    print(f"🤖 Groq: {'✅' if client else '❌'}")
    print(f"🏦 SUNAT: {session_manager['status']}")
    print("="*60)
    print("\n📌 Endpoints disponibles:")
    print("   POST /comparar           - Comparar PDF vs XML + extraer datos")
    print("   POST /sunat/individual   - Consulta individual SUNAT")
    print("   POST /sunat/masivo       - Consulta masiva SUNAT")
    print("   GET  /sunat/status       - Estado de sesión SUNAT")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=(env=='LOCAL'))

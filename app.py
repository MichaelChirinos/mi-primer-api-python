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
import base64

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
    pdf_content = None
    xml_content = None
    pdf_filename = "archivo_sap.pdf"
    xml_filename = "archivo_sap.xml"

    try:
        # 1. DETERMINAR EL ORIGEN DE LOS DATOS (JSON de Power Automate o Files de Manual/SharePoint)
        if request.is_json:
            print("📦 Recibido formato JSON (Base64 desde Power Automate/SAP)")
            data = request.get_json()
            
            # Extraemos de la estructura enviada por el SP de SQL
            archivos = data.get('archivos', {})
            info_sap = data.get('info_sap', {})
            
            if 'pdf_base64' in archivos and 'xml_base64' in archivos:
                try:
                    pdf_content = base64.b64decode(archivos['pdf_base64'])
                    xml_content = base64.b64decode(archivos['xml_base64'])
                    # Usamos los nombres que vienen del SQL o genéricos
                    pdf_filename = archivos.get('pdf_name', 'factura_sap.pdf').replace('/', '')
                    xml_filename = archivos.get('xml_name', 'factura_sap.xml').replace('/', '')
                except Exception as e:
                    return jsonify({'error': f'Error decodificando Base64: {str(e)}'}), 400
            else:
                return jsonify({'error': 'Faltan campos pdf_base64 o xml_base64 en el JSON'}), 400
        
        elif 'pdf' in request.files and 'xml' in request.files:
            print("📎 Recibido formato multipart/form-data (Carga manual)")
            pdf_file = request.files['pdf']
            xml_file = request.files['xml']
            pdf_filename = pdf_file.filename
            xml_filename = xml_file.filename
            pdf_content = pdf_file.read()
            xml_content = xml_file.read()
        
        else:
            return jsonify({'error': 'No se encontraron archivos PDF y XML en la petición'}), 400

        # 2. CREAR ARCHIVOS TEMPORALES PARA PROCESAMIENTO
        # Necesitamos archivos físicos para que fitz (PyMuPDF) pueda leerlos
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
            tmp_pdf.write(pdf_content)
            pdf_path = tmp_pdf.name
            temp_paths.append(pdf_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp_xml:
            tmp_xml.write(xml_content)
            xml_path = tmp_xml.name
            temp_paths.append(xml_path)

        # 3. EXTRACCIÓN DE TEXTO DEL PDF
        print(f"📄 Extrayendo texto de: {pdf_filename}")
        pdf_text = ""
        with fitz.open(pdf_path) as doc:
            for page in doc:
                pdf_text += page.get_text()
        
        # 4. EXTRACCIÓN DE TEXTO DEL XML
        print(f"🧬 Extrayendo texto de: {xml_filename}")
        try:
            xml_text = xml_content.decode('utf-8')
        except UnicodeDecodeError:
            xml_text = xml_content.decode('latin-1')

        # Limitamos el texto para no exceder el contexto de Groq (20k caracteres es seguro)
        pdf_limitado = pdf_text[:20000]
        xml_limitado = xml_text[:20000]

        # 5. CONSTRUCCIÓN DEL PROMPT PARA GROQ
        prompt_unificado = f"""
        Eres un auditor de facturación electrónica peruana experto en SAP Business One.

        **CONTEXTO DE ARCHIVOS**
        - Archivo PDF: {pdf_filename}
        - Archivo XML: {xml_filename}

        **CONTENIDO EXTRAÍDO DEL PDF:**
        {pdf_limitado}

        **CONTENIDO EXTRAÍDO DEL XML:**
        {xml_limitado}

        **TAREA:**
        Compara los datos del PDF visual contra los datos estructurales del XML. 
        Verifica RUC emisor, Serie-Número, Fecha, Moneda y Monto Total.

        Responde EXACTAMENTE con este formato:

        ===ANALISIS===
        [Tu análisis detallado de discrepancias o coincidencias en markdown]

        ===DATOS_SUNAT===
        {{
            "numRuc": "RUC del emisor",
            "codComp": "01",
            "numeroSerie": "Serie (ej: F001)",
            "numero": "Número (ej: 1234)",
            "fechaEmision": "DD/MM/YYYY",
            "monto": "Monto total",
            "tiene_discrepancias": true/false
        }}
        """

        print("🤖 Llamando a Groq (Llama 3.3 70B)...")
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un auditor de control de calidad de facturas. Tu precisión es vital para la contabilidad."},
                {"role": "user", "content": prompt_unificado}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1, # Temperatura baja para mayor precisión en datos
            max_tokens=3000
        )

        respuesta_ia = completion.choices[0].message.content

        # 6. PARSEAR RESPUESTA DE LA IA
        resultado_analisis = "Error al procesar el análisis"
        datos_extraidos = {}
        tiene_discrepancias = True

        if '===DATOS_SUNAT===' in respuesta_ia:
            partes = respuesta_ia.split('===DATOS_SUNAT===')
            resultado_analisis = partes[0].replace('===ANALISIS===', '').strip()
            
            json_str = re.search(r'\{.*\}', partes[1], re.DOTALL)
            if json_str:
                try:
                    datos_extraidos = json.loads(json_str.group())
                    tiene_discrepancias = datos_extraidos.get('tiene_discrepancias', True)
                except json.JSONDecodeError:
                    print("❌ Error al decodificar JSON de la IA")

        # 7. RETORNAR RESULTADO UNIFICADO
        return jsonify({
            'status': 'success',
            'pdf_procesado': pdf_filename,
            'xml_procesado': xml_filename,
            'analisis_ia': resultado_analisis,
            'datos_para_sunat': datos_extraidos,
            'alerta_discrepancia': tiene_discrepancias,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"❌ ERROR CRÍTICO: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

    finally:
        # Limpieza de archivos temporales para no llenar el disco
        for path in temp_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"Cleaned up: {path}")
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

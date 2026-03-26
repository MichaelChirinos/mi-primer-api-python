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

app = Flask(__name__)
CORS(app)

# Configurar Groq
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
# ENDPOINT: COMPARAR PDF vs XML + EXTRACCIÓN DE DATOS
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
        
        # Extraer texto del PDF
        print("\nExtrayendo texto del PDF...")
        pdf_text = ""
        doc = fitz.open(pdf_path)
        for page in doc:
            pdf_text += page.get_text()
        doc.close()
        print(f"PDF extraído: {len(pdf_text)} caracteres")
        
        # Extraer texto del XML
        print("Extrayendo texto del XML...")
        xml_text = ""
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_text = f.read()
        print(f"XML extraído: {len(xml_text)} caracteres")
        
        # Limitar textos
        pdf_limitado = pdf_text[:20000]
        xml_limitado = xml_text[:20000]
        
        # ============================================
        # PROMPT ÚNICO: Comparación + Extracción de datos en UNA SOLA LLAMADA
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
            "numeroSerie": "Serie",
            "numero": "Número",
            "fechaEmision": "DD/MM/YYYY",
            "monto": "Monto total",
            "tiene_discrepancias": true/false
        }}

        **REGLAS IMPORTANTES:**
        1. En el análisis, compara línea por línea ambos archivos
        2. Lista campos que coinciden y discrepancias
        3. Da veredicto final: APROBADA/REVISAR/RECHAZADA
        4. En DATOS_SUNAT, extrae los datos del XML (prioridad)
        5. Si algún dato no existe, pon "NO_ENCONTRADO"
        6. "tiene_discrepancias" debe ser TRUE si hay alguna diferencia, FALSE si todo coincide
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
        print(f"Respuesta recibida, longitud: {len(respuesta)}")
        
        # ============================================
        # EXTRAER ANÁLISIS Y DATOS
        # ============================================
        resultado_analisis = respuesta
        datos_extraidos = None
        tiene_discrepancias = True  # Por defecto True
        
        # Buscar sección ===DATOS_SUNAT===
        if '===DATOS_SUNAT===' in respuesta:
            partes = respuesta.split('===DATOS_SUNAT===')
            resultado_analisis = partes[0].replace('===ANALISIS===', '').strip()
            
            # Extraer JSON de la segunda parte
            json_texto = partes[1].strip()
            try:
                # Buscar JSON con regex
                json_match = re.search(r'\{.*\}', json_texto, re.DOTALL)
                if json_match:
                    datos_extraidos = json.loads(json_match.group())
                    tiene_discrepancias = datos_extraidos.get('tiene_discrepancias', True)
                    print(f"✅ Datos extraídos: {datos_extraidos}")
                    print(f"✅ Tiene discrepancias: {tiene_discrepancias}")
                else:
                    raise Exception("No se encontró JSON")
            except Exception as e:
                print(f"Error parseando JSON: {e}")
                datos_extraidos = {
                    "numRuc": "ERROR_PARSEO",
                    "codComp": "ERROR_PARSEO",
                    "numeroSerie": "ERROR_PARSEO",
                    "numero": "ERROR_PARSEO",
                    "fechaEmision": "ERROR_PARSEO",
                    "monto": "ERROR_PARSEO",
                    "tiene_discrepancias": True
                }
                tiene_discrepancias = True
        else:
            # Si no encuentra el separador, intentar extraer del texto
            print("⚠️ No se encontró el separador ===DATOS_SUNAT===")
            try:
                # Buscar JSON en toda la respuesta
                json_match = re.search(r'\{[^{}]*"numRuc"[^{}]*\}', respuesta, re.DOTALL)
                if json_match:
                    datos_extraidos = json.loads(json_match.group())
                    tiene_discrepancias = datos_extraidos.get('tiene_discrepancias', True)
            except:
                datos_extraidos = None
                tiene_discrepancias = True
        
        # ============================================
        # DETERMINAR SI HAY DISCREPANCIAS (fallback)
        # ============================================
        # Si el JSON no tenía tiene_discrepancias, calcularlo del análisis
        if datos_extraidos and datos_extraidos.get('tiene_discrepancias') is None:
            if "no se encontraron diferencias" in resultado_analisis.lower() or "coinciden" in resultado_analisis.lower():
                tiene_discrepancias = False
            else:
                tiene_discrepancias = True
        
        # ============================================
        # RESPUESTA FINAL
        # ============================================
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
# PÁGINA PRINCIPAL
# ============================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'api': 'Factura Validator',
        'version': '2.0.0',
        'endpoints': {
            'comparar': 'POST /comparar (requiere pdf + xml)'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🚀 API iniciada en puerto {port}")
    print(f"📌 Endpoint: POST /comparar")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=port, debug=True)

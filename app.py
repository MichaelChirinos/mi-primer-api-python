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
        

        prompt_comparacion = f"""
        Eres un auditor especializado en facturación electrónica.

        **ARCHIVOS A COMPARAR**
        - PDF: {pdf_file.filename}
        - XML: {xml_file.filename}

        **CONTENIDO EXTRAÍDO DEL PDF**
        {pdf_limitado}

        **CONTENIDO EXTRAÍDO DEL XML**
        {xml_limitado}

        **CAMPOS OBLIGATORIOS A VERIFICAR:**
        - RUC del emisor
        - RUC del receptor/cliente
        - Número de factura (serie y número)
        - Fecha de emisión
        - Moneda
        - Total valor de venta (subtotal)
        - IGV
        - Importe total

        **FORMATO DE RESPUESTA:**

        📊 RESUMEN DE COMPARACIÓN
        Archivo PDF: {pdf_file.filename}
        Archivo XML: {xml_file.filename}
        Fecha de análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        ✅ CAMPOS QUE COINCIDEN
        • RUC Emisor: [valor PDF] | [valor XML]
        • RUC Cliente: [valor PDF] | [valor XML]
        • Número Factura: [valor PDF] | [valor XML]
        • Fecha Emisión: [valor PDF] | [valor XML]
        • Moneda: [valor PDF] | [valor XML]
        • Total Venta: [valor PDF] | [valor XML]
        • IGV: [valor PDF] | [valor XML]
        • Importe Total: [valor PDF] | [valor XML]

        ❌ DISCREPANCIAS ENCONTRADAS
        • [Campo]: PDF dice "[valor]" | XML dice "[valor]"

        🏁 VEREDICTO FINAL
        [APROBADA / REVISAR / RECHAZADA]
        """
        
        print("\n🤖 Llamando a Groq para comparación...")
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un auditor experto en facturación electrónica."},
                {"role": "user", "content": prompt_comparacion}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=4000
        )
        
        resultado_analisis = completion.choices[0].message.content
        print("✅ Comparación completada")

        print("\n🤖 Extrayendo datos estructurados del XML...")
        
        prompt_datos = f"""
        Extrae los siguientes datos del XML de factura electrónica.
        
        CONTENIDO XML:
        {xml_limitado}
        
        Responde SOLO con este JSON, sin texto adicional:
        {{
            "numRuc": "RUC del emisor (11 dígitos)",
            "codComp": "01",
            "numeroSerie": "Serie del comprobante",
            "numero": "Número del comprobante",
            "fechaEmision": "Fecha en formato DD/MM/YYYY",
            "monto": "Monto total con dos decimales"
        }}
        
        Si algún dato no existe en el XML, pon "NO_ENCONTRADO".
        """
        
        completion_datos = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un extractor de datos. Responde SOLO con JSON válido."},
                {"role": "user", "content": prompt_datos}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
            max_tokens=500
        )
        
        # Parsear respuesta JSON
        try:
            datos_extraidos = json.loads(completion_datos.choices[0].message.content)
            print(f"✅ Datos extraídos: {datos_extraidos}")
        except Exception as e:
            print(f"Error al parsear JSON: {e}")
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
            'datos_extraidos': datos_extraidos
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
        'version': '1.0.0',
        'endpoints': {
            'comparar': 'POST /comparar (requiere pdf + xml)'
        },
        'datos_extraidos': {
            'numRuc': 'RUC del emisor',
            'codComp': 'Código de comprobante (01=Factura)',
            'numeroSerie': 'Serie del comprobante',
            'numero': 'Número del comprobante',
            'fechaEmision': 'Fecha en formato DD/MM/YYYY',
            'monto': 'Monto total'
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🚀 API iniciada en puerto {port}")
    print(f"📌 Endpoint: POST /comparar")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=port, debug=True)

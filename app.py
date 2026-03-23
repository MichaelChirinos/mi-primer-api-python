from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os
import tempfile
from werkzeug.utils import secure_filename
import traceback
import fitz  # PyMuPDF
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configurar Groq con la variable de entorno
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
if not GROQ_API_KEY:
    print("ERROR CRÍTICO: GROQ_API_KEY no está configurada")
else:
    print(f"GROQ_API_KEY configurada correctamente (termina en ...{GROQ_API_KEY[-4:]})")

client = Groq(api_key=GROQ_API_KEY)

# Configuración de archivos permitidos
ALLOWED_EXTENSIONS = {'pdf', 'xml'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================
# ENDPOINT 1: SALUDO (original)
# ============================================
@app.route('/saludar', methods=['POST'])
def saludar():
    try:
        datos = request.get_json()
        nombre = datos.get('nombre', '')
        
        if not nombre:
            return jsonify({'error': 'Falta el nombre'}), 400
            
        return jsonify({
            'recibido': nombre,
            'saludo': f'¡Hola {nombre}! Python te saluda'
        })
    except Exception as e:
        print(f"Error en /saludar: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================
# ENDPOINT 2: IA (preguntas)
# ============================================
@app.route('/ia', methods=['POST'])
def ia():
    try:
        datos = request.get_json()
        pregunta = datos.get('pregunta', '')
        
        if not pregunta:
            return jsonify({'error': 'Falta la pregunta'}), 400
        
        if not GROQ_API_KEY:
            return jsonify({'error': 'GROQ_API_KEY no está configurada'}), 500
        
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente útil que responde en español de forma clara y concisa."
                },
                {
                    "role": "user",
                    "content": pregunta
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=500
        )
        
        respuesta = chat_completion.choices[0].message.content
        
        return jsonify({
            'respuesta': respuesta,
            'pregunta': pregunta,
            'modelo': 'llama3-70b-8192'
        })
        
    except Exception as e:
        print(f"Error en /ia: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================
# ENDPOINT 3: PROCESAR ARCHIVO INDIVIDUAL
# ============================================
@app.route('/procesar-archivo', methods=['POST'])
def procesar_archivo():
    print("\n=== NUEVA PETICIÓN A /procesar-archivo ===")
    print(f"Headers recibidos: {dict(request.headers)}")
    print(f"Files keys: {list(request.files.keys())}")
    print(f"Form keys: {list(request.form.keys())}")
    
    temp_path = None
    try:
        # 1. Verificar que viene un archivo
        print("1. Verificando archivo en request.files...")
        if 'archivo' not in request.files:
            print("ERROR: No se encontró el campo 'archivo'")
            return jsonify({'error': 'No se envió ningún archivo'}), 400
        
        file = request.files['archivo']
        print(f"2. Archivo recibido: {file.filename}")
        print(f"   - Content-Type: {file.content_type}")
        print(f"   - Content-Length: {file.content_length if file.content_length else 'desconocido'}")
        
        if file.filename == '':
            print("ERROR: Nombre de archivo vacío")
            return jsonify({'error': 'Nombre de archivo vacío'}), 400
        
        # 2. Validar extensión
        print("3. Validando extensión...")
        if not allowed_file(file.filename):
            print(f"   ERROR: Extensión no permitida: {file.filename}")
            return jsonify({'error': 'Tipo de archivo no permitido. Solo PDF o XML'}), 400
        print(f"   ✅ Extensión válida")
        
        # 3. Validar tamaño
        print("4. Validando tamaño...")
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        print(f"   Tamaño: {file_size} bytes")
        if file_size > MAX_FILE_SIZE:
            print(f"   ERROR: Archivo demasiado grande: {file_size} > {MAX_FILE_SIZE}")
            return jsonify({'error': f'Archivo demasiado grande. Máximo {MAX_FILE_SIZE//1024//1024}MB'}), 400
        print(f"   ✅ Tamaño válido")
        
        # 4. Guardar temporalmente
        print("5. Guardando archivo temporal...")
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        print(f"   Nombre seguro: {filename}")
        print(f"   Extensión: {file_ext}")
        
        # Leer el contenido directamente del archivo
        file_content = file.read()
        print(f"   Tamaño del contenido leído: {len(file_content)} bytes")
        
        # Crear archivo temporal y escribir el contenido
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}', mode='wb') as tmp:
            bytes_escritos = tmp.write(file_content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = tmp.name
            print(f"   Bytes escritos: {bytes_escritos}")
            print(f"   Archivo guardado en: {temp_path}")
        
        # 5. Extraer texto según tipo
        print(f"\n6. Extrayendo texto de archivo tipo: {file_ext}")
        texto_extraido = ""
        
        if file_ext == 'pdf':
            try:
                print("   Procesando PDF con PyMuPDF...")
                doc = fitz.open(temp_path)
                num_pages = len(doc)
                print(f"   PDF tiene {num_pages} páginas")
                
                for page_num in range(num_pages):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    texto_extraido += page_text
                    print(f"   Página {page_num+1}: {len(page_text)} caracteres")
                
                doc.close()
                print(f"   ✅ PDF procesado: {len(texto_extraido)} caracteres totales")
                
            except Exception as e:
                print(f"   ERROR al leer PDF: {str(e)}")
                traceback.print_exc()
                return jsonify({'error': f'Error al leer PDF: {str(e)}'}), 500
        
        elif file_ext == 'xml':
            try:
                print("   Leyendo archivo XML...")
                with open(temp_path, 'r', encoding='utf-8') as xml_file:
                    texto_extraido = xml_file.read()
                    print(f"   XML leído: {len(texto_extraido)} caracteres")
            except Exception as e:
                print(f"   ERROR al leer XML: {str(e)}")
                traceback.print_exc()
                return jsonify({'error': f'Error al leer XML: {str(e)}'}), 500
        
        if not texto_extraido.strip():
            print("   ERROR: No se pudo extraer texto del archivo")
            return jsonify({'error': 'No se pudo extraer texto del archivo'}), 400
        
        print(f"   ✅ Texto extraído: {len(texto_extraido)} caracteres")
        
        # 6. Limitar texto
        texto_limitado = texto_extraido[:10000]
        print(f"7. Texto limitado a {len(texto_limitado)} caracteres")
        
        # 7. Enviar a Groq
        print("8. Enviando a Groq para análisis...")
        pregunta_analisis = f"""
        Analiza el siguiente contenido de archivo y proporciona un resumen estructurado.
        
        Tipo de archivo: {file_ext.upper()}
        Nombre: {filename}
        
        Contenido:
        {texto_limitado}
        
        Por favor, proporciona:
        1. Un resumen breve del contenido
        2. Los puntos clave o datos más importantes
        """
        
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un asistente especializado en analizar archivos PDF y XML."},
                {"role": "user", "content": pregunta_analisis}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=1000
        )
        
        resultado = completion.choices[0].message.content
        print(f"   ✅ Respuesta de Groq: {len(resultado)} caracteres")
        
        # 8. Devolver resultado
        print("=== PETICIÓN COMPLETADA EXITOSAMENTE ===\n")
        return jsonify({
            'resultado': resultado,
            'archivo': filename,
            'tipo': file_ext,
            'tamano': file_size
        })
        
    except Exception as e:
        print(f"ERROR GENERAL: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"✅ Archivo temporal eliminado: {temp_path}")
            except Exception as e:
                print(f"⚠️ Error al eliminar archivo temporal: {e}")

# ============================================
# ENDPOINT 4: COMPARAR PDF vs XML (MEJORADO)
# ============================================
@app.route('/comparar', methods=['POST'])
def comparar():
    print("\n=== NUEVA PETICIÓN A /comparar ===")
    print(f"Headers recibidos: {dict(request.headers)}")
    print(f"Files keys: {list(request.files.keys())}")
    
    temp_paths = []
    try:
        # Verificar que vienen ambos archivos
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
        
        print(f"Tamaño PDF: {len(pdf_content)} bytes")
        print(f"Tamaño XML: {len(xml_content)} bytes")
        
        # Guardar PDF temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as tmp:
            tmp.write(pdf_content)
            tmp.flush()
            os.fsync(tmp.fileno())
            pdf_path = tmp.name
            temp_paths.append(pdf_path)
            print(f"PDF guardado en: {pdf_path}")
        
        # Guardar XML temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xml', mode='wb') as tmp:
            tmp.write(xml_content)
            tmp.flush()
            os.fsync(tmp.fileno())
            xml_path = tmp.name
            temp_paths.append(xml_path)
            print(f"XML guardado en: {xml_path}")
        
        # Extraer texto del PDF
        print("\nExtrayendo texto del PDF...")
        pdf_text = ""
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pdf_text += page.get_text()
            doc.close()
            print(f"PDF extraído: {len(pdf_text)} caracteres")
        except Exception as e:
            print(f"Error en PDF: {e}")
            return jsonify({'error': f'Error al leer PDF: {str(e)}'}), 500
        
        # Extraer texto del XML
        print("Extrayendo texto del XML...")
        xml_text = ""
        try:
            with open(xml_path, 'r', encoding='utf-8') as f:
                xml_text = f.read()
            print(f"XML extraído: {len(xml_text)} caracteres")
        except Exception as e:
            print(f"Error en XML: {e}")
            return jsonify({'error': f'Error al leer XML: {str(e)}'}), 500
        
        # Limitar textos
        pdf_limitado = pdf_text[:8000]
        xml_limitado = xml_text[:8000]
        
        # ============================================================
        # PROMPT CON FORMATO LINEAL (SIN TABLAS)
        # ============================================================
        prompt = f"""
        Eres un auditor especializado en facturación electrónica con 15 años de experiencia. Tu tarea es comparar una factura en formato PDF (visual) y su correspondiente XML (datos estructurados).

        ### ARCHIVOS A COMPARAR
        - **PDF**: {pdf_file.filename}
        - **XML**: {xml_file.filename}

        ### CONTENIDO EXTRAÍDO
        === PDF ===
        {pdf_limitado}
        
        === XML ===
        {xml_limitado}

        ### INSTRUCCIONES ESTRICTAS
        Realiza una comparación exhaustiva siguiendo este orden:

        1. **CAMPOS CLAVE A VERIFICAR** (obligatorio):
           - RUC del emisor
           - RUC del receptor/cliente
           - Número de factura
           - Fecha de emisión
           - Fecha de vencimiento (si existe)
           - Moneda
           - Total valor de venta (subtotal)
           - IGV (monto de impuesto)
           - Importe total

        2. **POR CADA CAMPO**, indica:
           - ✅ **Coincidencia**: si el valor es el mismo en ambos formatos
           - ❌ **Discrepancia**: si los valores difieren (muestra PDF vs XML)

        3. **DISCREPANCIAS GRAVES**:
           - Si algún campo obligatorio no existe en alguno de los formatos
           - Si hay diferencias en el total o IGV (mayores a 0.01 por redondeo)
           - Si los RUC no coinciden (esto invalida la factura)

        4. **FORMATO DE RESPUESTA** (usar exactamente este formato, SIN TABLAS):

        📊 RESUMEN DE COMPARACIÓN
        Archivo PDF: {pdf_file.filename}
        Archivo XML: {xml_file.filename}
        Fecha de análisis: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        ✅ CAMPOS QUE COINCIDEN
        • RUC Emisor: [valor]
        • RUC Cliente: [valor]
        • Número Factura: [valor]
        • Fecha Emisión: [valor]
        • Moneda: [valor]
        • Total Venta: [valor]
        • IGV: [valor]
        • Importe Total: [valor]

        ❌ DISCREPANCIAS ENCONTRADAS
        • [Campo 1]: PDF dice "[valor PDF]" | XML dice "[valor XML]"
        • [Campo 2]: PDF dice "[valor PDF]" | XML dice "[valor XML]"
        (Si no hay discrepancias, poner: "No se encontraron discrepancias.")

        📌 CAMPOS FALTANTES
        • [Campo 1]: presente en [PDF/XML], ausente en [XML/PDF]
        (Si no hay campos faltantes, poner: "No se encontraron campos faltantes.")

        🏁 VEREDICTO FINAL
        [Conclusión clara y concisa. Usar uno de estos tres estados obligatoriamente: APROBADA, REVISAR, RECHAZADA]

        REGLAS PARA VEREDICTO:
        - Si discrepancia en RUC del emisor → RECHAZADA
        - Si hay campos faltantes importantes → REVISAR
        """
        
        # Llamar a Groq
        print("\nLlamando a Groq para comparación...")
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "Eres un auditor experto en facturación electrónica. Responde ÚNICAMENTE en español. Usa el formato lineal con viñetas (•) que se te indica. Sé preciso y conciso."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            max_tokens=2500
        )
        
        resultado = completion.choices[0].message.content
        print(f"✅ Comparación completada: {len(resultado)} caracteres")
        
        # Devolver resultado
        return jsonify({
            'resultado': resultado,
            'pdf': pdf_file.filename,
            'xml': xml_file.filename,
            'fecha': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"ERROR GENERAL: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Limpiar archivos temporales
        for path in temp_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"✅ Archivo temporal eliminado: {path}")
                except:
                    pass
# ============================================
# ENDPOINT 5: PÁGINA PRINCIPAL
# ============================================
@app.route('/', methods=['GET'])
def home():
    return "API funcionando con Groq! Endpoints disponibles: /saludar (POST), /ia (POST), /procesar-archivo (POST), /comparar (POST)"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Iniciando servidor en puerto {port}")
    print(f"GROQ_API_KEY configurada: {'SÍ' if GROQ_API_KEY else 'NO'}")
    app.run(host='0.0.0.0', port=port)

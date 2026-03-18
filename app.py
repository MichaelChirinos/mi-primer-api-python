from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os
import tempfile
from werkzeug.utils import secure_filename
import traceback
import fitz  # PyMuPDF

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

@app.route('/', methods=['GET'])
def home():
    return "API funcionando con Groq! Endpoints: /saludar (POST), /ia (POST) y /procesar-archivo (POST)"

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
        
        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
            print(f"   Archivo guardado en: {temp_path}")
            print(f"   Tamaño en disco: {os.path.getsize(temp_path)} bytes")
        
        # 5. Extraer texto según tipo
        print(f"6. Extrayendo texto de archivo tipo: {file_ext}")
        texto_extraido = ""
        
        if file_ext == 'pdf':
            try:
                print("   Procesando PDF con PyMuPDF...")
                
                # Abrir el PDF con PyMuPDF
                doc = fitz.open(temp_path)
                num_pages = len(doc)
                print(f"   PDF tiene {num_pages} páginas")
                
                # Extraer texto de cada página
                for page_num in range(num_pages):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    texto_extraido += page_text
                    print(f"   Página {page_num+1}: {len(page_text)} caracteres")
                
                doc.close()
                print(f"   ✅ PDF procesado: {len(texto_extraido)} caracteres totales")
                
            except Exception as e:
                print(f"   ERROR al leer PDF con PyMuPDF: {str(e)}")
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
        
        # 6. Limitar texto (Groq tiene límites)
        texto_limitado = texto_extraido[:10000]  # 10k caracteres máx
        print(f"7. Texto limitado a {len(texto_limitado)} caracteres")
        
        # 7. Enviar a Groq para análisis
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
        3. Si es XML, muestra la estructura principal
        """
        
        try:
            # Verificar que el cliente Groq existe
            if not client:
                print("   ERROR: El cliente Groq no está inicializado")
                return jsonify({'error': 'Cliente Groq no disponible'}), 500
            
            print("   Llamando a Groq API...")
            completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un asistente especializado en analizar archivos PDF y XML."
                    },
                    {
                        "role": "user",
                        "content": pregunta_analisis
                    }
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=1000
            )
            
            resultado = completion.choices[0].message.content
            print(f"   ✅ Respuesta de Groq: {len(resultado)} caracteres")
            
        except Exception as e:
            print(f"   ERROR al llamar a Groq: {str(e)}")
            traceback.print_exc()
            return jsonify({'error': f'Error en Groq: {str(e)}'}), 500
        
        # 8. Devolver resultado
        print("9. Devolviendo respuesta exitosa")
        print("=== PETICIÓN COMPLETADA EXITOSAMENTE ===\n")
        return jsonify({
            'resultado': resultado,
            'archivo': filename,
            'tipo': file_ext,
            'tamano': file_size
        })
        
    except Exception as e:
        print(f"ERROR GENERAL NO CAPTURADO: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Limpiar archivo temporal
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"✅ Archivo temporal eliminado: {temp_path}")
            except Exception as e:
                print(f"⚠️ Error al eliminar archivo temporal: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Iniciando servidor en puerto {port}")
    print(f"GROQ_API_KEY configurada: {'SÍ' if GROQ_API_KEY else 'NO'}")
    app.run(host='0.0.0.0', port=port)

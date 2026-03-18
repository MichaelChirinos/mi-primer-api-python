from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os
import tempfile
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configurar Groq con la variable de entorno
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

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
        return jsonify({'error': str(e)}), 500
@app.route('/', methods=['GET'])
def home():
    return "API funcionando con Groq! Endpoints: /saludar (POST) y /ia (POST)"

# Configuración de archivos permitidos
ALLOWED_EXTENSIONS = {'pdf', 'xml'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/procesar-archivo', methods=['POST'])
def procesar_archivo():
    temp_path = None
    try:
        # 1. Verificar que viene un archivo
        if 'archivo' not in request.files:
            return jsonify({'error': 'No se envió ningún archivo'}), 400
        
        file = request.files['archivo']
        if file.filename == '':
            return jsonify({'error': 'Nombre de archivo vacío'}), 400
        
        # 2. Validar extensión
        if not allowed_file(file.filename):
            return jsonify({'error': 'Tipo de archivo no permitido. Solo PDF o XML'}), 400
        
        # 3. Validar tamaño
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'Archivo demasiado grande. Máximo {MAX_FILE_SIZE//1024//1024}MB'}), 400
        
        # 4. Guardar temporalmente
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
        
        # 5. Extraer texto según tipo
        texto_extraido = ""
        
        if file_ext == 'pdf':
            try:
                import PyPDF2
                with open(temp_path, 'rb') as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    for page in reader.pages:
                        texto_extraido += page.extract_text()
            except Exception as e:
                return jsonify({'error': f'Error al leer PDF: {str(e)}'}), 500
        
        elif file_ext == 'xml':
            try:
                with open(temp_path, 'r', encoding='utf-8') as xml_file:
                    texto_extraido = xml_file.read()
            except Exception as e:
                return jsonify({'error': f'Error al leer XML: {str(e)}'}), 500
        
        if not texto_extraido.strip():
            return jsonify({'error': 'No se pudo extraer texto del archivo'}), 400
        
        # 6. Limitar texto (Groq tiene límites)
        texto_limitado = texto_extraido[:10000]  # 10k caracteres máx
        
        # 7. Enviar a Groq para análisis
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
        
        # Usar el cliente de Groq que ya tienes
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
        
        # 8. Devolver resultado
        return jsonify({
            'resultado': resultado,
            'archivo': filename,
            'tipo': file_ext,
            'tamano': file_size
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Limpiar archivo temporal
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

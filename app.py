from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import os

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

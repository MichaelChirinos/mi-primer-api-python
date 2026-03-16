from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/hola', methods=['POST'])
def hola():
    datos = request.get_json()
    nombre = datos.get('nombre')
    
    mensaje = f"¡Hola {nombre}! Python te saluda"
    
    return jsonify({
        "saludo": mensaje,
        "recibido": nombre
    })

@app.route('/', methods=['GET'])
def inicio():
    return "Mi API está funcionando!"
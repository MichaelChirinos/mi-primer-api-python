@app.route('/procesar-archivo', methods=['POST'])
def procesar_archivo():
    print("=== INICIO DE PETICIÓN /procesar-archivo ===")
    print(f"Headers: {request.headers}")
    print(f"Files keys: {request.files.keys()}")
    print(f"Form keys: {request.form.keys()}")
    
    temp_path = None
    try:
        # 1. Verificar que viene un archivo
        print("Verificando archivo en request...")
        if 'archivo' not in request.files:
            print("ERROR: No se encontró 'archivo' en request.files")
            return jsonify({'error': 'No se envió ningún archivo'}), 400
        
        file = request.files['archivo']
        print(f"Archivo recibido: {file.filename}")
        print(f"Tamaño: {file.content_length}")
        print(f"Content-Type: {file.content_type}")
        
        if file.filename == '':
            print("ERROR: Nombre de archivo vacío")
            return jsonify({'error': 'Nombre de archivo vacío'}), 400
        
        # 2. Validar extensión
        print("Validando extensión...")
        if not allowed_file(file.filename):
            print(f"ERROR: Extensión no permitida: {file.filename}")
            return jsonify({'error': 'Tipo de archivo no permitido. Solo PDF o XML'}), 400
        
        # 3. Validar tamaño
        print("Validando tamaño...")
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        print(f"Tamaño: {file_size} bytes")
        if file_size > MAX_FILE_SIZE:
            print(f"ERROR: Archivo demasiado grande: {file_size}")
            return jsonify({'error': f'Archivo demasiado grande. Máximo {MAX_FILE_SIZE//1024//1024}MB'}), 400
        
        # 4. Guardar temporalmente
        print("Guardando archivo temporal...")
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        print(f"Nombre seguro: {filename}, extensión: {file_ext}")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp:
            file.save(tmp.name)
            temp_path = tmp.name
            print(f"Archivo guardado en: {temp_path}")
        
        # 5. Extraer texto según tipo
        print(f"Extrayendo texto de archivo tipo: {file_ext}")
        texto_extraido = ""
        
        if file_ext == 'pdf':
            try:
                print("Intentando importar PyPDF2...")
                import PyPDF2
                print("PyPDF2 importado correctamente")
                
                with open(temp_path, 'rb') as pdf_file:
                    reader = PyPDF2.PdfReader(pdf_file)
                    num_pages = len(reader.pages)
                    print(f"PDF tiene {num_pages} páginas")
                    
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text()
                        texto_extraido += page_text
                        print(f"Página {i+1}: {len(page_text)} caracteres")
                        
            except Exception as e:
                print(f"ERROR al leer PDF: {str(e)}")
                return jsonify({'error': f'Error al leer PDF: {str(e)}'}), 500
        
        elif file_ext == 'xml':
            try:
                print("Leyendo archivo XML...")
                with open(temp_path, 'r', encoding='utf-8') as xml_file:
                    texto_extraido = xml_file.read()
                    print(f"XML leído: {len(texto_extraido)} caracteres")
            except Exception as e:
                print(f"ERROR al leer XML: {str(e)}")
                return jsonify({'error': f'Error al leer XML: {str(e)}'}), 500
        
        if not texto_extraido.strip():
            print("ERROR: No se pudo extraer texto del archivo")
            return jsonify({'error': 'No se pudo extraer texto del archivo'}), 400
        
        # 6. Limitar texto
        texto_limitado = texto_extraido[:10000]
        print(f"Texto limitado: {len(texto_limitado)} caracteres")
        
        # 7. Enviar a Groq
        print("Enviando a Groq...")
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
            print(f"Respuesta de Groq: {len(resultado)} caracteres")
            
        except Exception as e:
            print(f"ERROR al llamar a Groq: {str(e)}")
            return jsonify({'error': f'Error en Groq: {str(e)}'}), 500
        
        # 8. Devolver resultado
        print("=== PETICIÓN COMPLETADA EXITOSAMENTE ===")
        return jsonify({
            'resultado': resultado,
            'archivo': filename,
            'tipo': file_ext,
            'tamano': file_size
        })
        
    except Exception as e:
        print(f"ERROR GENERAL NO CAPTURADO: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"Archivo temporal eliminado: {temp_path}")
            except Exception as e:
                print(f"Error al eliminar archivo temporal: {e}")

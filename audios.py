import streamlit as st
import fitz
import pytesseract
from pytesseract import Output
from PIL import Image
import io
import os
import asyncio
import edge_tts
import tempfile
import re

if os.name == 'nt': 
    possible_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(possible_path):
        pytesseract.pytesseract.tesseract_cmd = possible_path

st.set_page_config(page_title="PDF a Audio con IA", page_icon="🎙️")

async def generar_audio(texto, archivo_salida, voz):
    try:
        comunicador = edge_tts.Communicate(texto, voz)
        await comunicador.save(archivo_salida)
    except Exception as e:
        raise Exception(f"Error al generar audio: {str(e)}")

def ocr_imagen(imagen):
    try:
        return pytesseract.image_to_string(imagen, lang='spa')
    except:
        return pytesseract.image_to_string(imagen, lang='eng')

def corregir_orientacion(img):
    try:
        datos_osd = pytesseract.image_to_osd(img, output_type=Output.DICT)
        rotacion_necesaria = datos_osd["rotate"]
        
        if rotacion_necesaria != 0:
            img = img.rotate(rotacion_necesaria, expand=True)
            return img, True
    except Exception:
        pass
    return img, False

def limpiar_texto(texto):
    """Limpia el texto para que sea compatible con TTS"""
    texto_limpio = re.sub(r'(?<!\.)[\n\r]+', ' ', texto)
    texto_limpio = re.sub(r'\.[\n\r]+', '. ', texto_limpio)
    texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()
    texto_limpio = re.sub(r'[^\w\s.,;:¿?¡!áéíóúÁÉÍÓÚñÑüÜ()-]', '', texto_limpio)
    return texto_limpio

def procesar_pdf(archivo_pdf, es_doble_pagina, auto_rotar):
    doc = fitz.open(stream=archivo_pdf.read(), filetype="pdf")
    texto_total = ""
    num_paginas = len(doc)
    
    barra_progreso = st.progress(0, text="Iniciando escaneo...")
    
    for i, pagina in enumerate(doc):
        progreso = (i + 1) / num_paginas
        barra_progreso.progress(progreso, text=f"Procesando página {i+1} de {num_paginas}...")
        
        pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        
        if auto_rotar:
            img, roto = corregir_orientacion(img)
        
        if es_doble_pagina:
            ancho, alto = img.size
            if ancho > alto:
                mitad = ancho // 2
                
                pag_izq = img.crop((0, 0, mitad, alto))
                pag_der = img.crop((mitad, 0, ancho, alto))
                
                texto_total += ocr_imagen(pag_izq) + " " + ocr_imagen(pag_der) + " "
            else:
                texto_total += ocr_imagen(img) + " "
        else:
            texto_total += ocr_imagen(img) + " "
    
    barra_progreso.progress(1.0, text="¡Lectura completada!")
    return texto_total

st.title("🎙️ Tu Conversor Personal de PDF a Audio")
st.markdown("Convierte libros escaneados, apuntes y PDFs en audiolibros realistas.")

with st.sidebar:
    st.header("⚙️ Configuración")
    
    voz_seleccionada = st.selectbox(
        "Voz del narrador:",
        options=[
            ('es-AR-TomasNeural', '🇦🇷 Tomás (Hombre)'),
            ('es-AR-ElenaNeural', '🇦🇷 Elena (Mujer)'),
            ('es-ES-AlvaroNeural', '🇪🇸 Álvaro (España)'),
            ('es-ES-ElviraNeural', '🇪🇸 Elvira (España)'),
            ('es-MX-DaliaNeural', '🇲🇽 Dalia (México)'),
            ('es-MX-JorgeNeural', '🇲🇽 Jorge (México)')
        ],
        format_func=lambda x: x[1]
    )
    
    st.divider()
    st.subheader("🔧 Opciones de Escaneo")
    
    activar_rotacion = st.checkbox(
        "🔄 Enderezar automáticamente", 
        value=True,
        help="Detecta si la hoja está de costado (horizontal) y la pone vertical antes de leer."
    )

    es_libro = st.checkbox(
        "📖 Separar doble página", 
        value=True,
        help="Marca esto si el PDF tiene dos páginas del libro en una sola hoja. El programa las cortará y leerá en orden."
    )

archivo_subido = st.file_uploader("Arrastra tu PDF aquí", type="pdf")

if archivo_subido is not None:
    st.success("✅ Archivo cargado.")
    
    if st.button("🎧 Convertir a Audio", type="primary", use_container_width=True):
        
        with st.spinner('⏳ La IA está leyendo, enderezando y convirtiendo tu libro...'):
            try:
                texto_extraido_crudo = procesar_pdf(archivo_subido, es_libro, activar_rotacion)
                
                texto_final = limpiar_texto(texto_extraido_crudo)
                
                if len(texto_final.strip()) < 10:
                    st.error("⚠️ Error: El texto extraído está vacío o es muy corto.")
                    st.info("Intenta con otro PDF o desactiva las opciones de escaneo.")
                else:
                    st.info(f"📄 Se extrajeron {len(texto_final)} caracteres.")
                    
                    with st.expander("Ver texto extraído (primeros 500 caracteres)"):
                        st.text(texto_final[:500])
                    
                    st.info("Generando audio...")
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                        ruta_temporal = tmp_file.name
                    
                    asyncio.run(generar_audio(texto_final, ruta_temporal, voz_seleccionada[0]))
                    
                    if os.path.exists(ruta_temporal) and os.path.getsize(ruta_temporal) > 0:
                        st.balloons()
                        st.success("¡Audio listo para escuchar!")
                        
                        st.audio(ruta_temporal, format="audio/mp3")
                        
                        with open(ruta_temporal, "rb") as file:
                            st.download_button(
                                label="⬇️ Descargar MP3",
                                data=file,
                                file_name="audiolibro_ia.mp3",
                                mime="audio/mp3",
                                use_container_width=True
                            )
                    else:
                        st.error("El archivo de audio no se generó correctamente.")
                        
            except Exception as e:
                st.error(f"❌ Ocurrió un error: {str(e)}")
                
                if "no audio" in str(e).lower():
                    st.warning("💡 Posibles soluciones:")
                    st.write("1. Verifica tu conexión a internet")
                    st.write("2. El texto puede contener caracteres no soportados")
                    st.write("3. Intenta con otra voz")
                elif "tesseract" in str(e).lower():
                    st.warning("Consejo: Verifica la instalación de Tesseract OCR.")
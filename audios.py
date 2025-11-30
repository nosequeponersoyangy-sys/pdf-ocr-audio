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
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

if os.name == 'nt': 
    possible_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(possible_path):
        pytesseract.pytesseract.tesseract_cmd = possible_path

st.set_page_config(
    page_title="PDF a Audio con IA", 
    page_icon="🎙️", 
    layout="wide"
)

async def generar_audio(texto, archivo_salida, voz):
    try:
        comunicador = edge_tts.Communicate(texto, voz)
        await comunicador.save(archivo_salida)
    except Exception as e:
        raise Exception(f"Error al generar audio: {str(e)}")

def ocr_imagen(imagen):
    try:
        config = '--psm 6 --oem 3'
        return pytesseract.image_to_string(imagen, lang='spa', config=config)
    except:
        return pytesseract.image_to_string(imagen, lang='eng', config=config)

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
    texto = re.sub(r'(\w)-\s*[\n\r]+\s*(\w)', r'\1\2', texto)
    texto = re.sub(r'(\w)-\s+(\w)', r'\1\2', texto)
    texto = re.sub(r'(?<!\.)[\n\r]+', ' ', texto)
    texto = re.sub(r'\.[\n\r]+', '. ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    texto = re.sub(r'[^\w\s.,;:¿?¡!áéíóúÁÉÍÓÚñÑüÜ()-]', '', texto)
    return texto

def detectar_tipo_pdf(doc):
    paginas_con_texto = 0
    paginas_muestra = min(3, len(doc))
    
    for i in range(paginas_muestra):
        texto = doc[i].get_text().strip()
        if len(texto) > 50:
            paginas_con_texto += 1
    
    es_nativo = paginas_con_texto >= (paginas_muestra * 0.66)
    return es_nativo, paginas_con_texto, paginas_muestra

def extraer_texto_nativo(pagina):
    return pagina.get_text()

def procesar_pagina_ocr(args):
    pagina, es_doble_pagina, auto_rotar, indice = args
    
    pix = pagina.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    
    if img.width > 2000:
        ratio = 2000 / img.width
        nuevo_ancho = int(img.width * ratio)
        nuevo_alto = int(img.height * ratio)
        img = img.resize((nuevo_ancho, nuevo_alto), Image.Resampling.LANCZOS)
    
    if auto_rotar:
        img, roto = corregir_orientacion(img)
    
    texto = ""
    if es_doble_pagina:
        ancho, alto = img.size
        if ancho > alto:
            mitad = ancho // 2
            pag_izq = img.crop((0, 0, mitad, alto))
            pag_der = img.crop((mitad, 0, ancho, alto))
            texto = ocr_imagen(pag_izq) + " " + ocr_imagen(pag_der) + " "
        else:
            texto = ocr_imagen(img) + " "
    else:
        texto = ocr_imagen(img) + " "
    
    return indice, texto

def procesar_pdf(archivo_pdf, es_doble_pagina, auto_rotar, usar_paralelo, forzar_ocr):
    doc = fitz.open(stream=archivo_pdf.read(), filetype="pdf")
    num_paginas = len(doc)
    
    st.info(f"📄 Documento con {num_paginas} páginas detectadas")
    
    if not forzar_ocr:
        es_nativo, pags_texto, pags_revisadas = detectar_tipo_pdf(doc)
        
        if es_nativo:
            st.success(f"✨ PDF con texto nativo detectado ({pags_texto}/{pags_revisadas} páginas con texto). Extracción rápida activada.")
            metodo = "nativo"
        else:
            st.warning("📸 PDF escaneado detectado. Usando OCR (más lento).")
            metodo = "ocr"
    else:
        st.info("🔧 Modo OCR forzado activado")
        metodo = "ocr"
    
    barra_progreso = st.progress(0, text="Iniciando extracción...")
    
    if metodo == "nativo":
        texto_total = ""
        for i in range(num_paginas):
            progreso = (i + 1) / num_paginas
            barra_progreso.progress(progreso, text=f"Extrayendo página {i+1} de {num_paginas}...")
            texto_total += extraer_texto_nativo(doc[i]) + " "
        
        barra_progreso.progress(1.0, text="¡Extracción completada!")
        return texto_total
    else:
        if usar_paralelo and num_paginas > 3:
            max_workers = min(multiprocessing.cpu_count(), 4)
            args_list = [(doc[i], es_doble_pagina, auto_rotar, i) for i in range(num_paginas)]
            textos_ordenados = [""] * num_paginas
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                resultados = executor.map(procesar_pagina_ocr, args_list)
                
                for indice, texto in resultados:
                    textos_ordenados[indice] = texto
                    progreso = (indice + 1) / num_paginas
                    barra_progreso.progress(progreso, text=f"OCR página {indice+1} de {num_paginas}...")
            
            texto_total = "".join(textos_ordenados)
        else:
            texto_total = ""
            for i in range(num_paginas):
                progreso = (i + 1) / num_paginas
                barra_progreso.progress(progreso, text=f"OCR página {i+1} de {num_paginas}...")
                indice, texto = procesar_pagina_ocr((doc[i], es_doble_pagina, auto_rotar, i))
                texto_total += texto
        
        barra_progreso.progress(1.0, text="¡OCR completado!")
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
    st.subheader("🔧 Opciones de Procesamiento")
    
    forzar_ocr = st.checkbox(
        "📸 Forzar OCR (para PDFs escaneados)", 
        value=False,
        help="Activa esto si el PDF está escaneado como imagen."
    )
    
    if forzar_ocr:
        activar_rotacion = st.checkbox(
            "🔄 Enderezar automáticamente", 
            value=True,
            help="Detecta si la hoja está de costado y la endereza."
        )
        es_libro = st.checkbox(
            "📖 Separar doble página", 
            value=True,
            help="Para PDFs con dos páginas del libro en una sola hoja."
        )
        usar_paralelo = st.checkbox(
            "⚡ Procesamiento paralelo", 
            value=True,
            help="Procesa múltiples páginas simultáneamente."
        )
    else:
        activar_rotacion = False
        es_libro = False
        usar_paralelo = True
        st.info("💡 Detección automática activada")
    
    st.divider()
    st.caption("📊 Límite: 200MB")

archivo_subido = st.file_uploader("Arrastra tu PDF aquí", type="pdf")

if archivo_subido is not None:
    tamano_mb = archivo_subido.size / (1024 * 1024)
    st.success(f"✅ Archivo cargado ({tamano_mb:.1f} MB)")
    
    if 'texto_extraido' not in st.session_state:
        st.session_state.texto_extraido = None
    
    if st.button("📖 Procesar PDF", type="primary", use_container_width=True):
        with st.spinner('⏳ Analizando y extrayendo texto...'):
            try:
                texto_extraido_crudo = procesar_pdf(
                    archivo_subido, 
                    es_libro, 
                    activar_rotacion, 
                    usar_paralelo,
                    forzar_ocr
                )
                texto_final = limpiar_texto(texto_extraido_crudo)
                
                if len(texto_final.strip()) < 10:
                    st.error("⚠️ Error: El texto extraído está vacío o es muy corto.")
                    st.info("💡 Intenta activar 'Forzar OCR' si el PDF está escaneado.")
                else:
                    st.session_state.texto_extraido = texto_final
                    palabras = len(texto_final.split())
                    st.success(f"✅ Texto extraído: {len(texto_final)} caracteres ({palabras} palabras)")
                    
            except Exception as e:
                st.error(f"❌ Error al procesar: {str(e)}")
    
    if st.session_state.texto_extraido:
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⬇️ Descargar Audio")
            if st.button("🎧 Generar MP3", use_container_width=True):
                with st.spinner('🎵 Generando audio...'):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                            ruta_temporal = tmp_file.name
                        
                        asyncio.run(generar_audio(
                            st.session_state.texto_extraido, 
                            ruta_temporal, 
                            voz_seleccionada[0]
                        ))
                        
                        if os.path.exists(ruta_temporal) and os.path.getsize(ruta_temporal) > 0:
                            st.balloons()
                            st.success("¡Audio listo!")
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
                        st.error(f"❌ Error: {str(e)}")
        
        with col2:
            st.subheader("📄 Ver Texto")
            if st.button("👁️ Mostrar texto extraído", use_container_width=True):
                st.text_area("Texto completo", st.session_state.texto_extraido, height=400)
        
        st.divider()
        with st.expander("🔍 Preview (primeros 500 caracteres)"):
            preview = st.session_state.texto_extraido[:500]
            st.text(preview)
            st.caption("✅ Palabras cortadas unificadas automáticamente")
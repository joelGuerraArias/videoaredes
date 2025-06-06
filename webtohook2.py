from dotenv import load_dotenv
load_dotenv() # Carga las variables de entorno desde el archivo .env

import streamlit as st
import cloudinary
import cloudinary.uploader
import requests
import tempfile
import subprocess
import os
from datetime import datetime, timedelta
import time
import re
import openai
from PIL import Image, ImageDraw, ImageFont

# Configuraciones generales
# Cargar configuraciones desde variables de entorno para mayor seguridad
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") # Asegúrate que este sea el ID numérico o el @username correcto
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validar que todas las variables de entorno necesarias estén configuradas
required_env_vars = {
    "CLOUDINARY_CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "CLOUDINARY_API_KEY": CLOUDINARY_API_KEY,
    "CLOUDINARY_API_SECRET": CLOUDINARY_API_SECRET,
    "WEBHOOK_URL": WEBHOOK_URL,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    "OPENAI_API_KEY": OPENAI_API_KEY
}

missing_vars = [name for name, value in required_env_vars.items() if value is None]

if missing_vars:
    st.error(f"Error: Faltan las siguientes variables de entorno: {', '.join(missing_vars)}. La aplicación no puede continuar.")
    st.stop()

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

# Utilidades
def clean_title(titulo):
    # Removida la línea problemática: titulo = titulo.replace("nmás", " más")
    titulo = re.sub(r"([a-zA-Z])\1{2,}", r"\1", titulo)
    titulo = re.sub(r':(?!\s)', ': ', titulo)  # Asegura espacio después de :
    return titulo.strip()

def generar_titulo_desde_caption(caption):
    caption = re.sub(r'\s+', ' ', caption.strip())
    return clean_title(caption[:caption.rfind(' ', 0, 100)] if ' ' in caption[:100] else caption[:100])

def generar_titulo_con_openai_desde_caption(caption, api_key):
    try:
        openai.api_key = api_key
        prompt = f"""
        Actúa como un experto en redacción de titulares periodísticos. A partir del siguiente caption, genera un título breve (máximo 100 caracteres), informativo y atractivo para redes sociales.
        No uses hashtags, emojis, ni repitas el caption. Agrega espacios después de signos de puntuación si hace falta.

        Caption: "{caption}"
        """
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto en crear títulos breves, claros y periodísticos para videos de noticias."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        titulo_generado = response.choices[0].message.content.strip()
        return clean_title(titulo_generado[:100])
    except Exception as e:
        st.warning(f"⚠️ No se pudo generar el título con OpenAI: {e}")
        return generar_titulo_desde_caption(caption)

def dividir_titulo(titulo, max_largo=50):
    """
    Divide el título en dos líneas si es muy largo
    """
    if len(titulo) <= max_largo:
        return titulo
    
    # Buscar el mejor punto de corte (espacio más cercano al centro)
    palabras = titulo.split()
    if len(palabras) == 1:
        return titulo  # No se puede dividir una sola palabra
    
    # Encontrar el punto de división más equilibrado
    total_chars = len(titulo)
    mejor_corte = 0
    menor_diferencia = float('inf')
    
    acumulado = 0
    for i, palabra in enumerate(palabras[:-1]):  # No incluir la última palabra
        acumulado += len(palabra) + 1  # +1 por el espacio
        diferencia = abs(acumulado - total_chars/2)
        if diferencia < menor_diferencia:
            menor_diferencia = diferencia
            mejor_corte = i + 1
    
    linea1 = " ".join(palabras[:mejor_corte])
    linea2 = " ".join(palabras[mejor_corte:])
    
    return f"{linea1}\\n{linea2}"  # Usar \\n para FFmpeg

def escape_ffmpeg_text(text):
    """
    Versión simplificada y segura para escapar texto en FFmpeg
    """
    # Solo escapamos lo esencial
    text = text.strip()
    text = text.replace(':', '\\:')      # Dos puntos
    text = text.replace("'", "\\'")     # Comilla simple  
    text = text.replace('"', '\\"')     # Comilla doble
    text = text.replace('\n', ' ')      # Convertir saltos de línea LITERALES (\n) a espacios
    text = text.replace('\r', '')       # Eliminar carriage returns
    # NO convertir '\\n' (string) a espacio, ya que dividir_titulo() lo usa para FFmpeg.
    # FFmpeg interpretará '\\n' como un salto de línea en el texto renderizado.
    
    # Remover caracteres especiales problemáticos pero mantener acentos y el carácter '\' (para \\n)
    # Se añade '\\' a la lista de caracteres permitidos para no eliminar las barras invertidas de '\\n'.
    text = re.sub(r'[^\w\s\-.,!?áéíóúüñÁÉÍÓÚÜÑ\\]', '', text)
    
    return text

def mostrar_preview_titulo(titulo):
    try:
        ancho, alto = 720, 128
        img = Image.new('RGB', (ancho, alto), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except:
            font = ImageFont.load_default()
        lines = titulo.split("\\n")  # Dividir por \\n para preview
        if len(lines) == 1:
            lines = titulo.split("\n")  # Fallback
        y = (alto - (len(lines) * 40)) // 2
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.rectangle([(ancho / 2 - w / 2 - 12, y - 6), (ancho / 2 + w / 2 + 12, y + 32)], fill=(0, 0, 0))
            draw.text(((ancho - w) / 2, y), line, font=font, fill=(255, 255, 255))
            y += 40
        st.image(img, caption="🖼️ Vista previa del título renderizado")
    except Exception as e:
        st.warning(f"⚠️ No se pudo generar la vista previa: {e}")

st.set_page_config(page_title="Batch de videos cada hora", layout="centered")
st.title("📆 Subir múltiples videos y publicarlos cada 1 hora automáticamente")

usar_openai = st.sidebar.checkbox("Usar OpenAI para generar títulos desde caption", value=True)
st.sidebar.info("OpenAI ayudará a generar títulos atractivos a partir del caption")

num_videos = st.number_input("¿Cuántos videos quieres subir?", min_value=1, max_value=10, step=1)
videos = []

for i in range(num_videos):
    st.subheader(f"🎬 Video #{i+1}")
    video_file = st.file_uploader(f"Selecciona el video #{i+1}", type=["mp4", "mov", "avi"], key=f"video_{i}")
    caption = st.text_area(f"Caption para el video #{i+1}", max_chars=2200, key=f"caption_{i}")

    title_key = f"title_{i}"
    session_title_key = f"generated_{title_key}"

    if session_title_key not in st.session_state:
        st.session_state[session_title_key] = ""

    st.text_input(f"Título para el video #{i+1} (opcional)",
                  value=st.session_state[session_title_key],
                  key=f"input_{title_key}")

    if st.button("🎯 Generar título desde caption", key=f"generate_button_{i}"):
        if caption.strip():
            with st.spinner("🧠 Generando título..."):
                nuevo_titulo = (
                    generar_titulo_con_openai_desde_caption(caption, OPENAI_API_KEY)
                    if usar_openai else
                    generar_titulo_desde_caption(caption)
                )
                st.session_state[session_title_key] = nuevo_titulo
                st.success("✅ Título generado con éxito")
                mostrar_preview_titulo(nuevo_titulo)
        else:
            st.warning("⚠️ Escribe un caption primero para generar un título.")

    char_count = len(st.session_state[session_title_key].strip())
    st.caption(f"🔤 {char_count}/100 caracteres")
    if char_count > 100:
        st.warning("⚠️ El título excede los 100 caracteres recomendados.")

    hashtag = st.selectbox(f"Hashtag predeterminado para el video #{i+1}", options=["#formula1rd", "#FVdigital"], key=f"hashtag_{i}")

    if video_file and caption:
        # Usar el título del campo de texto 'input_{title_key}', 
        # que puede haber sido editado por el usuario después de la generación automática.
        title_input_field_key = f"input_{title_key}"
        if title_input_field_key in st.session_state:
            title_raw = st.session_state[title_input_field_key].strip()
        else:
            # Fallback al título generado si el campo de input no existe en session_state 
            # (esto es poco probable si el st.text_input se renderizó)
            title_raw = st.session_state.get(session_title_key, "").strip()
        
        title = clean_title(title_raw)
        videos.append((video_file, f"{caption}\n\n{hashtag}", title))

start_hour = st.time_input("🕒 Hora inicial de publicación", value=datetime.now().time())

if st.button("🚀 Subir y comenzar publicación automática cada hora"):
    if not videos:
        st.warning("Debes subir al menos un video con caption.")
    else:
        now = datetime.now().replace(second=0, microsecond=0)
        start_time = now.replace(hour=start_hour.hour, minute=start_hour.minute)
        st.success(f"Iniciando batch de {len(videos)} videos desde las {start_time.strftime('%H:%M')}")

        for idx, (video_file, caption, title) in enumerate(videos):
            scheduled_time = start_time + timedelta(hours=idx)
            if 0 <= scheduled_time.hour < 6:
                scheduled_time = scheduled_time.replace(hour=6, minute=0)
                if scheduled_time < datetime.now():
                    scheduled_time += timedelta(days=1)

            st.info(f"⏳ Preparando video #{idx+1} para {scheduled_time.strftime('%Y-%m-%d %H:%M')}")

            with st.spinner("🎞️ Procesando video..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_input:
                    tmp_input.write(video_file.read())
                    input_path = tmp_input.name

                output_path = input_path.replace(".mp4", "_titled.mp4")

                # Procesar el título para FFmpeg
                titulo_final = dividir_titulo(title)
                titulo_ffmpeg = escape_ffmpeg_text(titulo_final)

                # Comando FFmpeg corregido
                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-vf", 
                    f"drawtext=text='{titulo_ffmpeg}':fontcolor=white:fontsize=18:box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h-(text_h*1.2)-30",
                    "-c:a", "copy", 
                    output_path
                ]

                # Ejecutar FFmpeg
                process = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if process.returncode != 0:
                    st.error(f"❌ Error procesando video #{idx+1}:\n{process.stderr.decode()}")
                    # Limpiar archivos temporales
                    try:
                        os.unlink(input_path)
                        if os.path.exists(output_path):
                            os.unlink(output_path)
                    except:
                        pass
                    continue

            with st.spinner("☁️ Subiendo a Cloudinary..."):
                try:
                    result = cloudinary.uploader.upload_large(output_path, resource_type="video", folder="webhook_batch")
                    video_url = result.get("secure_url")
                except Exception as e:
                    st.error(f"❌ Error subiendo video #{idx+1} a Cloudinary: {e}")
                    # Limpiar archivos temporales
                    try:
                        os.unlink(input_path)
                        os.unlink(output_path)
                    except:
                        pass
                    continue

            # Limpiar archivos temporales después de subir
            try:
                os.unlink(input_path)
                os.unlink(output_path)
            except:
                pass

            payload = {"video_url": video_url, "caption": caption, "title": title}
            st.subheader("📦 Payload enviado al webhook:")
            st.json(payload)

            try:
                response = requests.post(WEBHOOK_URL, json=payload, timeout=30)

                if response.status_code == 200:
                    st.success(f"✅ Publicado video #{idx+1} con éxito")

                    telegram_message = (
                        f"📹 *Video #{idx+1} publicado exitosamente*\n\n"
                        f"*Título:* {title}\n"
                        f"*Programado para:* {scheduled_time.strftime('%Y-%m-%d %H:%M')}\n"
                        f"*Link:* {video_url}\n"
                        f"*Caption:* {caption}"
                    )
                    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    telegram_data = {
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": telegram_message,
                        "parse_mode": "Markdown"
                    }
                    try:
                        telegram_response = requests.post(telegram_url, data=telegram_data, timeout=10)
                        if telegram_response.status_code == 200:
                            st.info("📬 Notificación enviada a Telegram")
                        else:
                            st.warning("⚠️ No se pudo enviar mensaje a Telegram")
                    except:
                        st.warning("⚠️ Error enviando mensaje a Telegram")

                else:
                    st.error(f"❌ Fallo al enviar video #{idx+1} (código {response.status_code})")

            except Exception as e:
                st.error(f"❌ Error enviando video #{idx+1}: {e}")

            # Esperar 1 hora antes del siguiente video (excepto el último)
            if idx < len(videos) - 1:
                st.warning("⏸️ Esperando 1 hora antes del siguiente video...")
                time.sleep(3600)

        st.balloons()
        st.success("🎉 Todos los videos han sido publicados automáticamente.")

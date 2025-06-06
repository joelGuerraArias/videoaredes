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
import imageio_ffmpeg as ffmpeg
from PIL import Image, ImageDraw, ImageFont

# --- Cargar secretos desde Streamlit Cloud ---
CLOUDINARY_CLOUD_NAME = st.secrets["CLOUDINARY_CLOUD_NAME"]
CLOUDINARY_API_KEY = st.secrets["CLOUDINARY_API_KEY"]
CLOUDINARY_API_SECRET = st.secrets["CLOUDINARY_API_SECRET"]
WEBHOOK_URL = st.secrets["WEBHOOK_URL"]
TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# --- Configurar servicios ---
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)
openai.api_key = OPENAI_API_KEY

# --- Funciones auxiliares ---
def escape_ffmpeg_text(text):
    text = text.strip()
    text = text.replace(':', '\\:').replace("'", "\\'").replace('"', '\\"')
    text = text.replace('\\n', '\n')
    text = re.sub(r'[^\w\s\-.,!?áéíóúüñÁÉÍÓÚÜÑ\\]', '', text)
    return text

def dividir_titulo(titulo, max_largo=50):
    if len(titulo) <= max_largo:
        return titulo
    palabras = titulo.split()
    if len(palabras) == 1:
        return titulo
    total_chars = len(titulo)
    mejor_corte = 0
    menor_diferencia = float('inf')
    acumulado = 0
    for i, palabra in enumerate(palabras[:-1]):
        acumulado += len(palabra) + 1
        diferencia = abs(acumulado - total_chars / 2)
        if diferencia < menor_diferencia:
            menor_diferencia = diferencia
            mejor_corte = i + 1
    linea1 = " ".join(palabras[:mejor_corte])
    linea2 = " ".join(palabras[mejor_corte:])
    return f"{linea1}\\n{linea2}"

def generar_titulo_con_openai(caption):
    try:
        prompt = f"""
        Actúa como un experto en redacción de titulares periodísticos. A partir del siguiente caption,
        genera un título breve (máximo 100 caracteres), informativo y atractivo para redes sociales.
        Caption: "{caption}"
        """
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto en crear títulos breves y periodísticos."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except:
        return caption[:100]

# --- Interfaz de usuario ---
st.title("📆 Publicador Automático de Videos")
caption = st.text_area("✍️ Escribe el caption del video")
usar_openai = st.checkbox("Usar OpenAI para generar título", value=True)
video_file = st.file_uploader("🎬 Sube el video (MP4)", type=["mp4"])

if st.button("🚀 Procesar y Publicar") and video_file and caption:
    title = generar_titulo_con_openai(caption) if usar_openai else caption[:100]
    titulo_final = dividir_titulo(title)
    titulo_ffmpeg = escape_ffmpeg_text(titulo_final)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(video_file.read())
        input_path = tmp.name
        output_path = input_path.replace(".mp4", "_titled.mp4")

    ffmpeg_path = ffmpeg.get_ffmpeg_exe()
    ffmpeg_cmd = [
        ffmpeg_path, "-y", "-i", input_path,
        "-vf", f"drawtext=text='{titulo_ffmpeg}':fontcolor=white:fontsize=22:x=(w-text_w)/2:y=h-(text_h*2):box=1:boxcolor=black@0.5",
        "-c:a", "copy",
        output_path
    ]

    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        st.error("❌ Error al procesar el video")
        st.text(result.stderr.decode())
        st.stop()

    with st.spinner("☁️ Subiendo a Cloudinary..."):
        upload = cloudinary.uploader.upload_large(output_path, resource_type="video", folder="webhook_batch")
        video_url = upload.get("secure_url")

    st.video(video_url)
    st.success("✅ Video subido exitosamente")

    # Enviar a Telegram
    telegram_message = f"🎥 *Nuevo video publicado!\nTítulo:* {title}\n\n{caption}\n\n🔗 {video_url}"
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(telegram_url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": telegram_message,
        "parse_mode": "Markdown"
    })

    # Webhook Make
    requests.post(WEBHOOK_URL, json={
        "video_url": video_url,
        "caption": caption,
        "title": title
    })

    st.balloons()
    st.success("🎉 Todo se ha publicado correctamente")

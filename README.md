# ⚡ Stream Auto Clipper & Multi-Social AI Publisher

Sistema backend completamente automatizado para detectar transmisiones en vivo (Twitch & Kick), extraer clips de los mejores momentos, editarlos dinámicamente en formato vertical 9:16 (con seguimiento de cámara del streamer y subtítulos dinámicos estilo TikTok) y compilarlos en videos de 10 minutos para YouTube, además de publicar en YouTube Shorts, Instagram Reels y TikTok.

---

## 🏛️ Arquitectura del Sistema

```
Twitch / Kick (En Vivo)
        │ (Webhooks / Polling cada 60s)
        ▼
   [Monitor] ──► Detecta "EN VIVO" y recolecta clips recientes
        │
        ▼
   [Downloader (yt-dlp / streamlink)] ──► Descarga archivo de video en bruto (.mp4)
        │
        ▼
   [Audio Transcriber (Whisper)] ──► Transcripción con timestamps palabra por palabra
        │
        ▼
   [AI Analyzer (Google Gemini Flash)] ──► Calcula Virality Score (1-10), Título Viral, Gancho y Hashtags
        │
        ▼
   [FaceCam Tracker (OpenCV / MediaPipe)] ──► Localiza la cámara del streamer para recortarla
        │
        ▼
   [Subtitle Generator] ──► Genera subtítulos `.ass` con palabra activa resaltada en amarillo
        │
        ▼
   [Video Processor (FFmpeg)] ──► Renderiza Short vertical 9:16 (1080x1920) con FaceCam + Gameplay
        │
        ├──► Publica a YouTube Shorts / Instagram Reels / TikTok
        └──► [Compiler] Concatena 5-10 clips en un video de 10 minutos para YouTube
```

---

## 🚀 Requisitos Previos e Instalación

### 1. Establecer el Directorio de Trabajo
Se recomienda abrir esta carpeta como tu espacio de trabajo activo en Antigravity IDE:
`C:\Users\TUF\.gemini\antigravity-ide\scratch\stream-auto-clipper`

### 2. Instalar FFmpeg (Si aún no está instalado en Windows)
Abre PowerShell y ejecuta:
```powershell
winget install Gyan.FFmpeg
```
*(O descarga FFmpeg y añade la carpeta `bin` a tu variable PATH o en la variable `FFMPEG_PATH` de tu `.env`).*

### 3. Instalar Dependencias de Python
En una terminal en la carpeta del proyecto:
```powershell
pip install -r requirements.txt
```

---

## ⚙️ Configuración (`.env`)

Copia o edita el archivo `.env`:

```env
# Servidor
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=True

# FFmpeg (Si no está en el PATH, especifica la ruta completa)
FFMPEG_PATH=ffmpeg

# Google Gemini API (Para evaluar potencial viral, títulos y hashtags)
# Obtén tu clave gratis en: https://aistudio.google.com/
GEMINI_API_KEY=tu_clave_gemini_aqui

# Whisper (Transcripción local de subtítulos)
# Opciones: tiny, base, small, medium
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu

# Twitch API (Opcional pero recomendado para detectar directos al instante)
# Consola: https://dev.twitch.tv/console/apps
TWITCH_CLIENT_ID=tu_client_id
TWITCH_CLIENT_SECRET=tu_client_secret

# YouTube Data API (Para subir videos y Shorts)
# Coloca tu archivo client_secret.json en credentials/client_secret.json
YOUTUBE_CLIENT_SECRETS_FILE=./credentials/client_secret.json

# Publicador Unificado (TikTok, Instagram, YouTube)
# Ayrshare es la vía más rápida sin lidiar con los procesos de revisión de Meta/TikTok:
AYRSHARE_API_KEY=tu_clave_ayrshare_opcional
```

---

## 🖥️ Ejecución y Dashboard Visual

Inicia el backend:

```powershell
python main.py
```

Abre tu navegador en:
👉 **`http://localhost:8000`**

### Funciones disponibles en el Dashboard:
1. **Monitoreo en Tiempo Real**: Ver qué canales están en vivo (🔴 EN VIVO) u offline.
2. **Agregar Canales**: Agrega cualquier usuario de Twitch o Kick con 1 clic.
3. **Escaneo Automático**: El planificador en segundo plano consulta el estado cada 60 segundos.
4. **Probar Clip Manual**: Pega el enlace de cualquier clip de Twitch o Kick para probar todo el pipeline de edición en segundos.
5. **Previsualizador de Video**: Reproduce los Shorts verticales 9:16 generados con subtítulos quemados directamente en el navegador.
6. **Publicación con 1 Clic**: Envía el clip a YouTube Shorts y redes conectadas.

---

## 📂 Estructura del Código

* `app/config.py`: Detección automática de FFmpeg, rutas de almacenamiento y variables de entorno.
* `app/database.py` y `app/models.py`: Base de datos SQLite (`clipper.db`) para trazabilidad de directos, clips y estados.
* `app/monitors/`: Monitores para Twitch (Helix API / EventSub) y Kick (API de canales y clips).
* `app/capture/`: Descargador seguro con `yt-dlp` y grabador de stream en vivo con `streamlink`.
* `app/ai/transcriber.py`: Transcripción de audio a texto con marcas de tiempo a nivel de palabra usando Whisper.
* `app/ai/analyzer.py`: Integración con Google Gemini para predecir viralidad y redactar títulos / ganchos.
* `app/ai/face_tracker.py`: Rastreador de rostro para aislar la cámara del streamer.
* `app/editor/subtitle_generator.py`: Generador de subtítulos `.ass` estilo TikTok con resaltado dinámico de palabra activa en color amarillo.
* `app/editor/video_processor.py`: Motor FFmpeg para transformar 16:9 en 9:16 (pantalla dividida o fondo desenfocado) con subtítulos integrados.
* `app/editor/compiler.py`: Unificador de clips para crear videos largos de 10 minutos para YouTube.
* `app/publishers/`: Integraciones con YouTube Data API v3 y redes sociales (Instagram Reels, TikTok, Ayrshare).
* `app/pipeline.py`: Orquestador central del flujo completo.
* `main.py`: Servidor FastAPI, endpoints REST y planificador en segundo plano.

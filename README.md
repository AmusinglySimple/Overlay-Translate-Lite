# Overlay Translate

Overlay Translate es una herramienta offline para capturar texto en pantalla, traducirlo en vivo y mostrarlo superpuesto de manera no intrusiva. Perfecta para traducción de contenido en vídeos, juegos, software o documentos sin necesidad de conexión a internet.

---

## Características principales

- ✨ Traducciones en vivo desde una región flotante
- 📸 Captura estática de pantalla para traducción puntual
- 🔍 OCR offline con PaddleOCR
- ⚖ Traducciones offline con LibreTranslate
- 🔧 Mejora de traducciones con modelos LLM locales (opcional)
- 🌐 Multilenguaje y detección automática
- ✅ Personalización de fuente, opacidad y contraste
- 🛠þ Soporte para snipping tool

---

## Requisitos del sistema

- Windows 10/11
- Python 3.9 o superior
- GPU no requerida (pero recomendada para OCR acelerado)
- 4 GB RAM mínimo (8 GB recomendado)

---

## Instalación

1. Clona este repositorio o copia los archivos en una carpeta.
2. Instala las dependencias:

```bash
pip install -r requirements.txt
```

3. Asegúrate de tener los siguientes elementos:
   - El modelo GGUF de LLM en `models/` (ej: `Phi-3.1-mini-128k-instruct-Q4_K_M.gguf`)
   - LibreTranslate instalado o ejecutándose en `http://127.0.0.1:5000`

4. Ejecuta la aplicación:

```bash
python main.py
```

---

## Uso rápido

- `F1`: Captura estática + traducir
- `F2`: Activar/desactivar clics a través de la región flotante
- `F4`: Herramienta de recorte (snip)
- `F5`: Alternar tema de alto contraste
- `F6`: Abrir el servidor de traducción
- `F8`: Alternar mejora de traducciones (si LLM está cargado)

Puedes configurar el idioma fuente y destino desde el menú *Settings*.

---

## requirements.txt

```
PyQt5>=5.15.7
paddleocr>=2.7.0 # Or latest stable version
transformers>=4.30.0
torch>=1.13.0
Pillow>=9.2.0
opencv-python>=4.6.0
langdetect>=1.0.9
requests>=2.28.1
libretranslate>=1.5.3
llama-cpp-python>=0.2.20 # Or latest stable version
```

---

## Notas adicionales

- Las capturas y traducciones se guardan temporalmente en el escritorio dentro de la carpeta `Support`.
- El modelo LLM es opcional, pero permite mejorar la calidad de traducción.
- Se recomienda ejecutar LibreTranslate en local para uso completamente offline.

---

## Licencia

Este proyecto es de uso personal. No redistribuir sin permiso del autor original.

---

## Contacto

Andrea - Master Hobby


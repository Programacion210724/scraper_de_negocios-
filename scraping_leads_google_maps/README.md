# 🚀 Google Maps Leads Extractor Pro

Una herramienta profesional de scraping automatizado para la extracción de leads de alta calidad desde Google Maps. Diseñada para ser rápida, robusta y fácil de desplegar.

## ✨ Características Principales

- **Extracción Inteligente:** Scroll automático para capturar grandes volúmenes de negocios.
- **Dashboard de Análisis:** Gráficos visuales de la distribución de categorías de tus leads.
- **Exportación Profesional:** Descarga tus resultados directamente en archivos Excel (.xlsx).
- **Exportación a Google Sheets:** Guarda tus leads directamente en una hoja de cálculo de Google.
- **Búsqueda en Tiempo Real:** Filtra tus resultados instantáneamente en la interfaz.
- **Arquitectura Robusta:** Manejo de errores, timeouts y rotación de User-Agents para evitar bloqueos.
- **Despliegue en un Click:** Totalmente dockerizado para funcionar en cualquier entorno.

## 🛠️ Requisitos

- [Docker](https://www.docker.com/get-started) instalado en tu máquina.

## 🚀 Instalación y Uso Rápido

No necesitas instalar Python ni ninguna librería. Solo sigue estos dos pasos:

1. **Levantar el contenedor:**
   Abre una terminal en la carpeta del proyecto y ejecuta:
   ```bash
   docker-compose up --build
   ```

2. **Acceder a la herramienta:**
   Una vez que veas el mensaje `Running on http://127.0.0.1:5000`, abre tu navegador y visita:
   👉 [http://localhost:5000](http://localhost:5000)

## 📊 Ejemplo de uso

1. Introduce la **Palabra Clave** (ej: `Dentistas`).
2. Introduce la **Ciudad** (ej: `Madrid`).
3. Define el **Límite** de negocios (ej: `50`).
4. Haz clic en **Extraer** y observa cómo se genera el dashboard de análisis.
5. Una vez finalizado, haz clic en **Descargar en Excel** o **Guardar en Google Sheets**.

## 📋 Configuración de Google Sheets

Para usar la funcionalidad de Google Sheets, sigue estos pasos:

1. **Crear proyecto en Google Cloud Console:**
   - Ve a https://console.cloud.google.com/
   - Crea un nuevo proyecto o selecciona uno existente
   - Habilita la API de Google Sheets para tu proyecto

2. **Crear credenciales OAuth 2.0:**
   - En "APIs y servicios" > "Credenciales", crea un "Cliente OAuth 2.0"
   - Tipo de aplicación: "Aplicación de escritorio"
   - Descarga el archivo `client_secret.json` y colócalo en la raíz del proyecto (junto a `app.py`)

3. **Configurar hoja de cálculo:**
   - Crea una hoja de cálculo en Google Sheets
   - Copia el ID de la hoja desde la URL (lo que está entre `/d/` y `/edit`)
   - Opcional: Define la variable de entorno `DEFAULT_SHEET_ID` con el ID de tu hoja para usarla por defecto

4. **Primera autenticación:**
   - Al ejecutar el contenedor con la aplicación, se abrirá una ventana del navegador para autorizar el acceso
   - El token se guardará en `token.json` para uso futuro

---
*Desarrollado profesionalmente para prospección de clientes de alto impacto.*
*Desarrollado profesionalmente para prospección de clientes de alto impacto.*

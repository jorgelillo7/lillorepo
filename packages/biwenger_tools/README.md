#  Biwenger Tools

## 🔥 ¿El salseo de tu liga Biwenger merece ser eterno? 🔥

¿Te molan los comunicados graciosos entre colegas para calentar vuestras ligas? ¿Os da rabia que se pierdan entre la publicidad o al reiniciar la temporada?

¡Aquí tienes la solución! Este proyecto es un sistema de **backup + web + análisis** para que vuestros mensajes más épicos, piques legendarios y análisis tácticos queden guardados y accesibles. Y sí, está hecho con un poco (mucho) de ayuda de la IA ;)

---

## 📜 Descripción del Proyecto

Este proyecto se divide en tres componentes principales que trabajan juntos para archivar, visualizar y analizar los datos de una liga de Biwenger.

1.  **Scraper de Mensajes (`scraper_job`):** Un script de Python automatizado que se conecta a Biwenger, extrae todos los comunicados, los categoriza (`comunicado`, `dato`, `cesion`), pre-procesa los datos de participación y guarda todo en archivos CSV en Google Drive.

2.  **Aplicación Web (`web-app`):** Una aplicación web ligera con Flask que lee los datos desde los archivos CSV y un Google Sheet para presentarlos en una interfaz limpia, elegante y totalmente responsive.

3.  **Analizador de Equipos (`teams-analyzer`):** Un potente script de análisis que utiliza Selenium para hacer scraping de datos avanzados de webs de análisis fantasy. Combina esta información con los datos de Biwenger para generar un informe detallado en CSV y enviarlo por Telegram.

---

## ✨ Características Principales

### Scraper de Mensajes (El Recolector Inteligente)

* **Autenticación Segura:** Inicia sesión en Biwenger de forma segura.
* **Categorización Inteligente:** Analiza los títulos de los mensajes y los clasifica automáticamente.
* **Pre-procesamiento de Datos:** Genera un archivo `participacion.csv` optimizado para que la web cargue las estadísticas al instante.
* **Almacenamiento en la Nube:** Guarda y actualiza los archivos CSV en Google Drive.
* **Automatización Total:** Diseñado para ser ejecutado como un **Cloud Run Job** y programado con **Cloud Scheduler**.
* **Gestión de Secretos:** Todas las credenciales se gestionan de forma segura a través de **Google Secret Manager**.

### Aplicación Web (El Portal de la Liga)

* **Interfaz Limpia:** Un diseño elegante y minimalista, con un tema claro para una legibilidad perfecta.
* **Múltiples Secciones:**
    * **Comunicados:** Visualiza los mensajes oficiales con paginación y búsqueda global.
    * **Salseo:** Una sección para los "Datos Curiosos" y las "Cesiones".
    * **Participación:** Un ranking que muestra un desglose de la participación de cada jugador.
    * **Palmarés:** Un resumen histórico de las temporadas pasadas.
    * **Ligas Especiales:** Lee y muestra datos de torneos especiales directamente desde un **Google Sheet**.
* **Configuración Centralizada:** Utiliza un archivo `config.py` y un `.env` para una gestión sencilla.
* **Desplegado en la Nube:** Alojado en **Cloud Run** para un rendimiento escalable y eficiente.

### Analizador de Equipos (El Espía Táctico)

* **Scraping Avanzado:** Utiliza **Selenium** para extraer datos de webs como "Analítica Fantasy" y "Jornada Perfecta".
* **Análisis 360º:** Evalúa no solo tu equipo, sino todas las plantillas de la liga y los jugadores libres en el mercado.
* **Enriquecimiento de Datos:** Cruza la información de Biwenger con métricas externas como coeficientes de rendimiento y puntuaciones esperadas.
* **Notificaciones por Telegram:** Envía el informe CSV final directamente a un chat de Telegram, para que tengas la ventaja táctica en tu móvil.
* **Ejecución Local:** Diseñado para ser ejecutado manualmente cuando necesites un análisis profundo antes de una jornada.

---

## 💻 Tecnologías Utilizadas

* **Backend (Scrapers):** Python, Requests, BeautifulSoup, **Selenium**, Unidecode, Google Cloud SDK.
* **Backend (Web):** Python, Flask.
* **Frontend:** HTML, Tailwind CSS, JavaScript.
* **Cloud y Despliegue:** Google Cloud Run (Jobs y Services), Cloud Scheduler, Secret Manager, Google Drive API, Google Sheets API, Docker.


| Acción                 | Comando                                                              | Descripción                      |
| ---------------------- | -------------------------------------------------------------------- | -------------------------------- |
| 🧪 Ejecutar tests      | `bazel test //packages/biwenger_tools/web:web_tests`                 | Corre pytest                     |
| 🏠 Servidor local      | `bazel run //packages/biwenger_tools/web:web_local`                  | Ejecuta en tu máquina            |
| 🐳 Imagen local        | `bazel run //packages/biwenger_tools/web:load_image_to_docker_local` | Build y carga en Docker          |
| ☁️ Subir a GCP         | `bazel run //packages/biwenger_tools/web:push_image_to_gcp`          | Build + Push a Artifact Registry |
| 📦 Imagen limpia local | `docker run --rm -p 8080:8080 bazel/web:local`                       | Ejecutar manualmente la imagen   |

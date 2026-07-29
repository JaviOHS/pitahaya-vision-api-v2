<!-- prettier-ignore -->
<div align="center">

# Pitahaya Vision — Backend API

![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092e20?style=flat-square&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/Django_REST_Framework-3.15-a02020?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14-4169e1?style=flat-square&logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

Orquestador central del ecosistema **Pitahaya Vision**. Gestiona autenticación, análisis fitosanitario, chatbot RAG, historial de plantas y administración de usuarios mediante una API REST segura y escalable.

[Instalacion](#instalacion) · [Arquitectura](#arquitectura) · [API](#endpoints) · [Seguridad](#seguridad) · [RAG](#base-de-conocimiento-rag)

</div>

---

## Descripcion

El backend actúa como orquestador entre el frontend React, el microservicio de visión artificial (FastAPI) y el servicio de chatbot (Gemma 3 en Google Colab). Implementa la lógica de negocio, persistencia de datos, autenticación por token y el pipeline de Retrieval-Augmented Generation (RAG) para respuestas contextuales.

> [!IMPORTANT]
> Este servicio depende del microservicio de análisis (puerto 8001) y del servicio de chatbot (Colab/ngrok) para funcionar correctamente.

## Arquitectura

```
pitahaya-vision-api-v2/
├── config/                  # Configuración Django, URLs, WSGI
│   ├── settings.py          # Settings centralizados
│   └── urls.py              # Enrutamiento /api/v2/
├── apps/
│   ├── security/            # Auth, usuarios, permisos, throttling
│   ├── analysis/            # Análisis de imágenes, proxy climático
│   ├── chatbot/             # Chat RAG, fincas, parcelas, contextos
│   └── rag/                 # Ingestión, embeddings, búsqueda semántica
├── knowledge_base/          # PDFs para la base de conocimiento
├── manage.py                # CLI de Django
└── requirements.txt         # Dependencias Python
```

### Flujo de Datos

```
Frontend (React)                    Microservicio FastAPI (:8001)
       │  POST /api/v2/analysis/              │
       ▼                                      ▼
┌──────────────────────┐             ┌─────────────────┐
│   Django Backend     │──predict──→ │  MobileNetV2    │
│   (Orquestador)      │←resultado── │  TensorFlow     │
│                      │             └─────────────────┘
│  · Autenticación     │
│  · Persistencia      │             Servicio Colab (ngrok)
│  · Notificaciones    │──chat────→  ┌─────────────────┐
│  · RAG retrieval     │←streaming── │  Gemma 3 4B     │
│                      │             │  + RAG context  │
└──────────────────────┘             └─────────────────┘
```

## Instalacion

### Requisitos

- Python 3.10+
- PostgreSQL (recomendado) o SQLite (desarrollo)
- Microservicio de análisis corriendo en puerto 8001
- Servicio de chatbot en Google Colab (ngrok)

### Configuracion

```bash
# Clonar y entrar al directorio
cd pitahaya-vision-api-v2

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores
```

### Base de Datos

```bash
# Ejecutar migraciones (crea todas las tablas)
python manage.py migrate

# Crear superuser (si no se auto-crea por señal)
python manage.py createsuperuser
```

### Base de Conocimiento RAG

```bash
# Ingestar todos los PDFs de knowledge_base/
python manage.py ingest_rag --auto

# Ingestar un archivo específico
python manage.py ingest_rag knowledge_base/enfermedades.pdf

# Forzar re-ingestión
python manage.py ingest_rag --auto --force
```

> [!NOTE]
> `ingest_rag` debe ejecutarse despues de `migrate` porque crea las tablas `RAG_DOCUMENT` y `RAG_CHUNK`.

### Iniciar el Servidor

```bash
python manage.py runserver
```

El servidor arranca en `http://localhost:8000`.

## Variables de Entorno

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `SECRET_KEY` | — | Clave secreta de Django (obligatorio) |
| `DEBUG` | `True` | Modo desarrollo |
| `DB_ENGINE` | `sqlite` | `sqlite` o `postgresql` |
| `DB_NAME` | `pitahaya_vision_db` | Nombre de la BD |
| `DB_USER` / `DB_PASSWORD` | — | Credenciales PostgreSQL |
| `SUPERUSER_USERNAME` | `admin` | Usuario admin auto-creado |
| `SUPERUSER_EMAIL` | — | Email del admin |
| `SUPERUSER_PASSWORD` | — | Contraseña del admin |
| `ANALYSIS_SERVICE_URL` | `http://localhost:8001` | URL del microservicio FastAPI |
| `ANALYSIS_SERVICE_TIMEOUT` | `60` | Timeout en segundos |
| `CHATBOT_SERVICE_URL` | — | URL del tunnel ngrok (Colab) |
| `CHATBOT_SERVICE_TIMEOUT` | `120` | Timeout del chatbot |
| `VISUAL_CROSSING_API_KEY` | — | API key de Visual Crossing |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Orígenes permitidos |
| `TOKEN_EXPIRY_HOURS` | `168` | Expiración del token (7 días) |
| `MAX_LOGIN_ATTEMPTS` | `5` | Intentos antes de bloqueo |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Duración del bloqueo |

## Endpoints

### Autenticacion (`/api/v2/auth/`)

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `POST` | `/login/` | Iniciar sesión (username o email) |
| `POST` | `/logout/` | Cerrar sesión |
| `POST` | `/registration/` | Registrar usuario (cuenta inactiva) |
| `POST` | `/registration/verify-email/` | Verificar email con token |
| `POST` | `/password/reset/` | Solicitar restablecimiento |
| `POST` | `/password/reset/confirm/` | Confirmar nueva contraseña |
| `GET` | `/user/` | Obtener datos del usuario |
| `PATCH` | `/user/` | Actualizar datos del usuario |
| `GET` | `/profile/` | Obtener perfil completo |
| `PATCH` | `/profile/` | Actualizar perfil (soporta FormData para foto) |
| `GET` | `/profile/preferences/` | Preferencias de notificaciones |
| `PATCH` | `/profile/preferences/` | Actualizar preferencias |
| `POST` | `/account/delete/` | Borrado lógico de cuenta |
| `GET` | `/availability/` | Verificar disponibilidad de campo |
| `GET` | `/customers/` | Admin: listar usuarios |
| `POST` | `/customers/{id}/toggle_active/` | Admin: activar/suspender |
| `POST` | `/customers/{id}/set_role/` | Admin: cambiar rol |

### Analisis (`/api/v2/analysis/`)

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `GET` | `/` | Listar análisis (filtros: range, date, user_name) |
| `POST` | `/` | Subir imagen y ejecutar clasificación |
| `GET` | `/{id}/` | Detalle de análisis |
| `PATCH` | `/{id}/` | Actualizar análisis |
| `DELETE` | `/{id}/` | Eliminar análisis |
| `GET` | `/weather/` | Proxy climático Visual Crossing |

### Chatbot (`/api/v2/chatbot/`)

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `GET/POST` | `/farms/` | CRUD de fincas |
| `GET/POST` | `/plots/` | CRUD de parcelas |
| `GET/POST` | `/contexts/` | CRUD de contextos agronómicos |
| `GET/POST` | `/conversations/` | CRUD de conversaciones |
| `GET/POST` | `/messages/` | CRUD de mensajes |
| `GET/POST` | `/plant-histories/` | CRUD de historial de plantas |
| `POST` | `/chat/` | Chat RAG síncrono |
| `POST` | `/chat/stream/` | Chat RAG con streaming SSE |
| `POST` | `/suggest/` | Generar preguntas de seguimiento |
| `POST` | `/heatmap-analysis/` | Análisis IA del mapa de calor |
| `GET` | `/export-backup/` | Exportar datos como JSON |
| `POST` | `/import-backup/` | Importar datos desde JSON |

### RAG (`/api/v2/rag/`)

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `GET` | `/documents/` | Documentos indexados |
| `GET` | `/documents/{id}/` | Detalle con fragmentos |
| `GET` | `/status/` | Estado del sistema RAG |
| `POST` | `/search/` | Búsqueda semántica |

## Modelos de Datos

| Modelo | Campos Clave | Descripcion |
|--------|-------------|-------------|
| `User` | dni, phone, profile_photo, email_verified, deactivated_at | Usuario extendido con validación ecuatoriana |
| `Profile` | notifications_enabled, notify_severity_threshold | Preferencias de notificaciones |
| `Farm` | name, location | Finca del productor |
| `Plot` | farm, name, hectares, gps_location, zone, rows | Parcela dentro de una finca |
| `Context` | plot, plant_key_or_id, affected_part, main_symptom, status | Contexto agronómico |
| `Conversation` | user, context, title | Conversación con el chatbot |
| `ChatMessage` | conversation, role, content, image_path | Mensaje del chat |
| `PlantHistory` | context, analysis_result, final_diagnosis, treatment_applied | Historial de tratamientos |
| `AnalysisResult` | user, image_path, disease_name_predicted, confidence, severity | Resultado de clasificación |
| `RagDocument` | title, source_path, file_hash, chunks_count | Documento indexado |
| `RagChunk` | document, text, embedding (BinaryField) | Fragmento con embedding |

## Base de Conocimiento RAG

El sistema RAG utiliza:

- **Modelo de embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones, soporte nativo en español)
- **Estrategia de chunking:** 400 palabras por fragmento, overlap de 60 palabras
- **Umbral de similitud:** 0.25 (coseno)
- **Top-K:** 4 fragmentos por consulta
- **Almacenamiento:** Embeddings como `float32` serializados en `BinaryField`

**Documentos de conocimiento:**
- `Enfermedades de la Pitahaya.pdf` — Referencia técnica de patologías
- `Normativa Nacional (INIAP y AGROCALIDAD).pdf` — Marco normativo agrícola

## Seguridad

| Mecanismo | Implementacion |
|-----------|---------------|
| Autenticación | `TokenAuthentication` con expiración configurable (default 168h) |
| Anti-fuerza bruta | Throttling (3/min login) + bloqueo de cuenta (5 fallos → 15 min) |
| Validación de entrada | Módulo 10 (cédula ecuatoriana), regex (teléfono), fortaleza (contraseña) |
| Historial de contraseñas | No reutilización de las últimas 5 (`PasswordHistoryValidator`) |
| Aislamiento de datos | `OwnerFilterMixin` — cada usuario solo ve sus registros |
| Protección de API keys | Proxy en Django para Visual Crossing y chatbot |
| Reintentos | Backoff exponencial (3 intentos) en clientes HTTP |
| Borrado lógico | `deactivated_at` preserva integridad referencial |
| Auto-desactivación | Impedida para administradores (`toggle_active`) |

## Desarrollo

### Estructura de Apps

```
apps/
├── security/        # 15+ archivos: models, views, serializers, throttles, utils, signals
├── analysis/        # 7 archivos: models, views, serializers, client, notifications
├── chatbot/         # 8 archivos: models, views, serializers, client, backup
└── rag/             # 8 archivos: models, views, embedder, retriever, loader, management command
```

### Comandos de Desarrollo

```bash
# Shell de Django
python manage.py shell

# Crear superuser
python manage.py createsuperuser

# Verificar estado RAG
curl http://localhost:8000/api/v2/rag/status/

# Verificar salud del microservicio
curl http://localhost:8001/health
```

### Panel de Administración

Disponible en `http://localhost:8000/admin/` con los modelos registrados:
- User, Profile, LoginAttempt, PasswordHistory
- Farm, Plot, Context, Conversation, ChatMessage, PlantHistory
- AnalysisResult
- RagDocument, RagChunk

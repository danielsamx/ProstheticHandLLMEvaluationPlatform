# Instalación y despliegue

**Idiomas:** [Español](instalacion.md) · [English](../en/installation.md)

---

## Requisitos

| Componente | Versión | Notas |
|---|---|---|
| Docker Engine | 24+ | Con Compose v2 |
| PostgreSQL | 17 | Lo proporciona Compose |
| Python | 3.13 | Solo para instalación nativa |
| Node.js | 22 | Solo para instalación nativa |
| LM Studio | actual | Opcional, pero es el entorno principal |

Alrededor de 4 GB de RAM para la plataforma en sí. Los modelos locales necesitan
bastante más: presupuesta para el modelo, no para esto.

---

## Arranque rápido con Docker

```bash
git clone <repositorio> TIC-LLM && cd TIC-LLM
cp .env.example .env          # edita SECRET_KEY y las claves de API que uses
docker compose up --build
```

| Servicio | URL |
|---|---|
| Interfaz | http://localhost:4200 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

Las migraciones y el seed se ejecutan solos al arrancar el backend.

---

## Configuración

`.env` lo leen tanto Compose como el backend. Ese doble papel importa y es el
origen del error de configuración más frecuente; ver el aviso más abajo.

### Base de datos

```bash
POSTGRES_USER=phlab
POSTGRES_PASSWORD=phlab          # cámbiala en cualquier despliegue compartido
POSTGRES_DB=prosthetic_lab
DATABASE_URL=postgresql+asyncpg://phlab:phlab@localhost:5432/prosthetic_lab
DATABASE_URL_SYNC=postgresql+psycopg://phlab:phlab@localhost:5432/prosthetic_lab
```

Dos URL porque la aplicación corre en asíncrono (`asyncpg`) y Alembic en síncrono
(`psycopg`).

### Aplicación

```bash
APP_ENV=development              # development | staging | production
LOG_LEVEL=INFO
SECRET_KEY=<cadena larga aleatoria>   # cámbiala antes de cualquier despliegue compartido
CORS_ORIGINS=["http://localhost:4200","http://127.0.0.1:4200"]
```

En desarrollo el backend acepta además orígenes de loopback y de red privada en
cualquier puerto. El navegador trata `localhost`, `127.0.0.1` y una dirección de
red como tres orígenes distintos, y una lista de coincidencia exacta convierte
una elección inofensiva de URL en el fallo de todas las peticiones sin ningún
error útil. Pon `CORS_ALLOW_LOCAL_ORIGINS=false` para desactivarlo. En producción
solo se aplica la lista explícita.

### Entornos de modelos locales

> **Déjalas comentadas.**
>
> Compose lee `.env` al resolver `${VAR:-default}`, así que un valor aquí
> **sobrescribe** el valor correcto de `docker-compose.yml`. Poner
> `LM_STUDIO_API_BASE=http://localhost:1234/v1` es la causa clásica de «LM Studio
> is not reachable»: dentro del contenedor, `localhost` es el contenedor.
>
> El backend además reescribe las direcciones de loopback a
> `host.docker.internal` cuando detecta que está en un contenedor, de modo que lo
> correcto es simplemente dejar la variable sin definir.

```bash
# LM_STUDIO_API_BASE=http://localhost:1234/v1
# OLLAMA_API_BASE=http://localhost:11434
```

| El backend corre | Dirección correcta |
|---|---|
| Nativo | `http://localhost:1234/v1` |
| En Docker | `http://host.docker.internal:1234/v1` |

`host.docker.internal` lo proporciona Docker Desktop; `docker-compose.yml` añade
el mapeo `host-gateway` para que el mismo nombre funcione en Linux nativo.

### Proveedores alojados

```bash
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

Define solo las que uses. LiteLLM las lee del entorno.

---

## Configurar LM Studio

1. Instala LM Studio y descarga un modelo. Buenos puntos de partida para esta
   tarea: Qwen2.5 7B Instruct, Llama 3.1 8B Instruct, Mistral 7B Instruct.
2. **Developer → Start Server**, puerto 1234.
3. Comprueba que el log lista los endpoints compatibles con OpenAI, en particular
   `GET http://localhost:1234/v1/models`.
4. En la interfaz, la etiqueta **LM Studio** se pone en ámbar.
5. Pulsa **Import loaded models**.

`litellm.drop_params` está activado, así que un runtime que ignore `top_k` o
`seed` degrada a «no aplicado» en vez de dar error, y el parámetro ignorado queda
registrado en la ejecución como `dropped_parameters` —porque si no, una corrida
parece reproducible sin serlo.

---

## Instalación nativa

### Backend

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

docker compose up -d db            # o apunta a tu propio PostgreSQL
alembic upgrade head
python -m app.seeds.seed

uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
```

Angular 22 exige TypeScript 6.0.x. Si `npm install` informa de un conflicto de
dependencia par en `typescript`, comprueba que `package.json` fija `~6.0.0`.

---

## Verificación

```bash
# Backend: 189 tests, sin necesidad de base de datos
cd backend && python -m pytest tests -q

# Comprobaciones estáticas del frontend: sin necesidad de node_modules
python scripts/check_frontend.py

# Todo
./scripts/check.sh
```

`scripts/check_frontend.py` detecta dos fallos de compilación que los tests
unitarios no pueden ver: un backtick suelto que cierra antes de tiempo el
template de un componente (NG1002 de Angular) y un import con alias de ruta
irresoluble.

---

## Despliegue en producción

### Antes de exponerlo

1. **`SECRET_KEY`** — larga y aleatoria.
2. **`APP_ENV=production`** — desactiva el regex permisivo de CORS local.
3. **`CORS_ORIGINS`** — los orígenes exactos, nada más.
4. **Contraseña de la base de datos** — que no sea la de por defecto.
5. **TLS** — termínalo en un proxy inverso.
6. **Copias de seguridad** — ver más abajo.

### Proxy inverso

```nginx
server {
    listen 443 ssl http2;
    server_name lab.example.edu;

    location / {
        proxy_pass http://localhost:4200;
    }

    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

`X-Forwarded-For` se respeta solo para procedencia: es falsificable y nunca se
usa para autorización.

El timeout largo del WebSocket importa: una sesión de adquisición en vivo puede
durar horas.

### Build del frontend

```bash
cd frontend && npm run build      # -> dist/prosthetic-lab
```

La configuración de producción intercambia `environment.prod.ts`, que resuelve la
API relativa al origen que sirve la aplicación, de modo que un proxy inverso no
necesita configuración adicional.

---

## Copias de seguridad

La base de datos **es** el registro científico. Perderla es perder todos los
experimentos.

```bash
# Volcado
docker compose exec -T db pg_dump -U phlab prosthetic_lab | gzip > backup-$(date +%F).sql.gz

# Restauración
gunzip -c backup-2026-07-28.sql.gz | docker compose exec -T db psql -U phlab prosthetic_lab
```

`executions.raw_response` y `emg_windows.samples` dominan el tamaño. Si hay que
podar, elimina esas columnas y conserva las filas: las métricas, los digests y
las entradas de auditoría son pequeños y son lo que el análisis lee de verdad.

---

## Actualización

```bash
git pull
docker compose down
docker compose up --build         # las migraciones corren al arrancar
```

`docker compose restart` no basta cuando han cambiado `.env`,
`docker-compose.yml` o `angular.json`: esos se leen al crear el contenedor y al
compilar, no al reiniciar el proceso. Usa `up -d --force-recreate` para cambios
de entorno.

---

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| «LM Studio is not reachable» | `LM_STUDIO_API_BASE` puesto a `localhost` en `.env` | Coméntalo; `up -d --force-recreate backend` |
| Todas las peticiones fallan, sin mensaje | CORS: la interfaz se abrió en otro origen | Usa `localhost:4200`, o revisa `CORS_ORIGINS` |
| Catálogo de modelos vacío | El backend se reinició después de cargar la página | Recarga; luego **Import loaded models** |
| Bucle de reinicio del backend en el seed | Un prompt generado cambió sin subir de versión | Corregido en `0003`; el seed archiva la deriva bajo una versión direccionada por contenido |
| `port is already allocated` | 4200, 8000 o 5432 en uso | Detén el otro proceso o remapea en `docker-compose.yml` |
| La migración `0002` falla | Es lo esperado: borra las ventanas EMG anteriores a la matriz | Un vector de características no se puede rellenar hacia una forma de onda sin fabricar datos |

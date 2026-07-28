# Base de datos

**Idiomas:** [Español](base-de-datos.md) · [English](../en/database.md)

PostgreSQL 17. Veintiuna tablas, tercera forma normal, con dos
desnormalizaciones deliberadas documentadas más abajo.

---

## Principios de diseño

**Nada se sobrescribe.** Las versiones de prompt, las ejecuciones y las entradas
de auditoría son solo-anexado. Un resultado publicado hace un año debe seguir
resolviendo a los bytes exactos que lo produjeron, lo que descarta las ediciones
en sitio.

**La identidad se congela.** Las filas que registran una acción guardan también
el correo del actor como texto, no solo una clave foránea. Las cuentas se borran;
el registro de quién ejecutó un experimento tiene que sobrevivir a eso.

**El borrado es lógico.** `projects.is_deleted` marca la fila; no se elimina
nada. Un borrado físico rompería justamente la trazabilidad que da sentido a la
plataforma.

**Las condiciones son consultables.** Los parámetros de decodificación viven a la
vez en `executions.model_snapshot` (JSONB, por fidelidad) y como columnas
tipadas (para hacer `GROUP BY temperature` sobre millones de filas). La
duplicación es intencionada y unidireccional: el snapshot es la fuente de verdad.

---

## Mapa del esquema

```
users
  │
  ├──< projects ──< experiments ──< executions ─┬─ validation_results ──< validation_issues
  │                                             ├─ execution_metrics
  │                                             ├─ execution_errors
  │                                             ├─ execution_logs
  │                                             ├─ simulator_movements
  │                                             └─ attachments
  │
  ├──< audit_logs
  └──< sampling_configurations >── llm_models >── llm_providers

emg_windows ──< executions          system_prompt_versions ──< executions
emg_stream_sessions                 technical_context_versions ──< executions
                                    dynamic_prompt_templates ──< executions
                                    lab_presets
```

---

## Tablas

### Identidad y organización

#### `users`
Cuentas de investigador. `role` es `admin`, `researcher` o `viewer`.

#### `projects`
Una línea de investigación.

| Columna | Notas |
|---|---|
| `slug` | Único, apto para URL, generado del nombre y desduplicado |
| `research_question` | Lo que hace legible el proyecto un año después |
| `status` | `active` / `paused` / `archived` |
| `owner_email` | Copia de identidad, sobrevive al borrado de la cuenta |
| `is_deleted`, `deleted_at` | Borrado lógico; la fila se conserva |
| `settings` | Valores por defecto JSONB que heredan los experimentos nuevos |

### Catálogo

#### `llm_providers`
Un proveedor enrutable por LiteLLM. `litellm_prefix` se antepone a la clave del
modelo (`lm_studio` + `qwen2.5-7b` → `lm_studio/qwen2.5-7b`). `is_local` gobierna
el reporte de coste: las corridas locales registran cero, y la métrica de
eficiencia pasan a ser los tokens por segundo.

#### `llm_models`
Un modelo concreto. Los indicadores `supports_*` son declaraciones de capacidad:
la interfaz deshabilita un parámetro que el runtime no puede respetar en lugar de
dejar que se descarte en silencio.

#### `sampling_configurations`
Una configuración de decodificación con nombre y reutilizable. Se guarda una vez
y se reproduce en todos los modelos, que es lo que mantiene controlada una
comparación.

### Artefactos de prompt versionados

`system_prompt_versions`, `technical_context_versions`, `dynamic_prompt_templates`

Forma común: `name`, `version`, `content`, `content_sha256`, `is_active`,
`is_system_default`. Únicos por `(name, version)`.

**Inmutables.** Editar en la interfaz inserta una fila nueva. Cuando el texto
generado cambia sin subir de versión, el seed lo archiva bajo `2.0.0+<sha8>` en
lugar de sobrescribir.

`technical_context_versions.limit_profile` registra qué envolvente mecánica
describe el texto, de modo que un contexto nunca puede emparejarse con un
validador que lo contradiga.

#### `lab_presets`
Paquete de un clic: configuración + tres versiones de prompt + mano + perfil de
límites.

### Estímulo

#### `emg_windows`
El estímulo experimental.

| Columna | Notas |
|---|---|
| `samples` | JSONB. Matriz N×8, amplitudes en [-1, 1] |
| `features` | **Desnormalización (1 de 2).** Descriptores cacheados, derivados de `samples`. Recalcular el RMS sobre millones de filas en cada consulta no es viable. |
| `checksum` | SHA-256 de matriz + frecuencia de muestreo. Demuestra que dos corridas vieron la misma señal |
| `ground_truth_gesture` | Permite puntuar la exactitud automáticamente |

#### `emg_stream_sessions`
Sesiones de adquisición en vivo.

### Experimentación

#### `experiments`
Fija un conjunto de condiciones congeladas: las tres versiones de prompt, el
perfil de límites, la lateralidad. `frozen_context_sha256` es la clave de
comparabilidad.

#### `executions`
Una inferencia independiente. La tabla central.

**Organización** — `project_id`, `experiment_id`, `repetition_index`,
`triggered_by_id`, `triggered_by_email`

**El prompt exacto enviado** — `system_prompt_text`, `technical_context_text`,
`dynamic_prompt_text`, `messages_json` y cinco digests SHA-256. Se guarda
literal, no se reconstruye: así el resultado sobrevive a la edición o el borrado
posterior de las filas a las que apuntaba.

**Modelo y endpoint** — `litellm_model`, `provider_slug`, `model_key`,
`api_base`, `api_flavour`, `model_snapshot`

**Parámetros de decodificación** — **Desnormalización (2 de 2).** `temperature`,
`top_p`, `top_k`, `max_tokens`, `seed`, `frequency_penalty`, `presence_penalty`,
`stop_sequences`, `response_format`, `reasoning_mode`, `custom_parameters`.
Duplicados desde `model_snapshot` para que un barrido de parámetros sea una
agregación SQL directa.

**`dropped_parameters`** — controles que el runtime ignoró en silencio. Sin esto,
una corrida parece reproducible sin serlo.

**Resultado** — `raw_response`, `parsed_response`, `finish_reason`, recuentos de
tokens, `cost_usd` (14,8 — las corridas locales son 0, las alojadas pueden ser
subcéntimo), `latency_ms`, `tokens_per_second`

**Origen** — `client_ip`, `user_agent`, `browser`, `operating_system`,
`device_type`, `session_id`, `request_id`, `app_version`

### Resultado

#### `validation_results` / `validation_issues`
Veredicto del pipeline de siete etapas, y una fila por incidencia. Agregar por
`code` es lo que convierte «falla el 30 % de las veces» en «falla porque
antepone prosa al JSON».

#### `execution_errors`
Fallos duros, categorizados: `provider`, `parse`, `schema`, `protocol`, `range`,
`kinematic`, `safety`, `internal`.

#### `execution_logs`
Las líneas de log que pertenecen al registro científico: un reintento, un
parámetro descartado, una respuesta que necesitó reparación. Ordenadas por
`sequence`, porque a esta resolución las marcas de tiempo colisionan.

#### `execution_metrics`
Medidas derivadas, en formato ancho por diseño para que la agregación entre
modelos sea un `GROUP BY` simple. Indicadores de cumplimiento, exactitud contra
la verdad de referencia, error de calibración, eficiencia y
`response_fingerprint`, el digest canónico que hace medible el determinismo.

#### `simulator_movements`
La pose realmente representada. **Solo existe una fila cuando la validación
pasó.** Su ausencia en una ejecución fallida es la prueba de auditoría de que la
barrera de seguridad se mantuvo.

### Gobernanza

#### `audit_logs`
Solo-anexado. Actor (id + copia del correo + rol), `action` de un catálogo
cerrado, `outcome`, `summary`, entidad afectada (tipo + id + copia de la
etiqueta), diff de `changes` por campo y origen completo de la petición.

`action` es una enumeración cerrada a propósito: el texto libre deriva hacia una
docena de grafías del mismo evento y deja de ser agregable.

Los secretos se redactan y los valores largos se resumen antes de llegar a
`changes`.

#### `attachments`
Archivos ligados a un proyecto, experimento o ejecución. Direccionados por
contenido; las cargas pequeñas en línea, las grandes por ruta.

---

## Consultas recurrentes

**Tabla comparativa entre modelos, con comparabilidad forzada**

```sql
SELECT litellm_model,
       count(*)                                            AS corridas,
       avg((validation_passed)::int)::numeric(5,4)         AS tasa_exito,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latencia,
       sum(total_tokens)                                   AS tokens,
       sum(cost_usd)                                       AS coste
FROM executions
WHERE experiment_id = $1
  AND frozen_context_sha256 = (
      SELECT frozen_context_sha256 FROM experiments WHERE id = $1
  )
GROUP BY litellm_model
ORDER BY tasa_exito DESC;
```

El predicado sobre `frozen_context_sha256` es lo que hace que el ranking
signifique algo.

**Cómo falla cada modelo**

```sql
SELECT e.litellm_model, i.stage, i.code, count(*) AS n
FROM executions e
JOIN validation_results r ON r.execution_id = e.id
JOIN validation_issues  i ON i.validation_result_id = r.id
WHERE i.severity = 'error' AND e.experiment_id = $1
GROUP BY 1, 2, 3
ORDER BY n DESC;
```

**Determinismo a temperatura 0**

```sql
SELECT m.repetition_group,
       count(DISTINCT m.response_fingerprint) AS respuestas_distintas,
       count(*)                               AS repeticiones
FROM execution_metrics m
JOIN executions e ON e.id = m.execution_id
WHERE e.temperature = 0 AND m.repetition_group IS NOT NULL
GROUP BY 1
HAVING count(DISTINCT m.response_fingerprint) > 1;
```

Las filas devueltas son corridas que deberían haber sido idénticas y no lo
fueron.

**Efecto de un parámetro**

```sql
SELECT temperature,
       avg((validation_passed)::int) AS tasa_exito,
       avg(latency_ms)               AS latencia_media
FROM executions
WHERE litellm_model = $1 AND frozen_context_sha256 = $2
GROUP BY temperature
ORDER BY temperature;
```

Esta es la consulta para la que existen las columnas desnormalizadas de
parámetros.

**Traza de auditoría de una entidad**

```sql
SELECT created_at, actor_email, action, outcome, summary, changes
FROM audit_logs
WHERE entity_type = 'project' AND entity_id = $1
ORDER BY created_at DESC;
```

---

## Migraciones

| Revisión | Contenido |
|---|---|
| `0001_initial` | Diecisiete tablas: el registro experimental básico |
| `0002_emg_matrix` | El estímulo pasa a ser una matriz cruda N×8; características derivadas, no aportadas |
| `0003_governance` | Proyectos, auditoría, adjuntos, logs de ejecución, metadatos de petición |

`0002` elimina las ventanas y ejecuciones existentes. Un vector de
características no determina la forma de onda de la que salió, así que rellenar
con una matriz sintética habría producido datos fabricados indistinguibles de los
grabados.

```bash
alembic upgrade head
alembic downgrade -1
alembic history --verbose
```

---

## Retención

Nada se borra automáticamente. En una estación con miles de ejecuciones,
`executions.raw_response` y `emg_windows.samples` dominan el almacenamiento. Si
hay que podar, elimina esas columnas y conserva la fila: las métricas, los
digests y las entradas de auditoría son pequeños y son lo que el análisis lee de
verdad.

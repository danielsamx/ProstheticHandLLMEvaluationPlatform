# Referencia de la API

**Idiomas:** [Español](api.md) · [English](../en/api.md)

Ruta base `/api/v1`. Documentación interactiva en `/docs` (Swagger) y `/redoc`.

Todos los cuerpos son JSON. Los errores siguen la forma de FastAPI:
`{"detail": "..."}` para un mensaje único, o una lista de errores de campo en los
fallos de validación.

Cualquier petición puede llevar `X-Request-ID` y `X-Session-ID`; ambos se
guardan en el registro de la ejecución y en la traza de auditoría, y
`X-Request-ID` vuelve en la respuesta para que un cliente pueda correlacionar sus
propios logs con los del servidor.

---

## Sistema

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/health` | Vitalidad. Responde «¿hay algo ahí?», no «¿funciona una consulta?» |
| `GET` | `/` | Metadatos del servicio y rutas WebSocket |

---

## Especificación del hardware

La prótesis tal como la entiende el backend. El simulador Angular construye su
rig a partir de esto, de modo que hay una única definición del hardware en todo
el sistema.

| Método | Ruta | Devuelve |
|---|---|---|
| `GET` | `/hand/spec` | Grados de libertad, actuadores, articulaciones, gestos, perfiles de límites, protocolo, envolvente de seguridad, formato EMG |
| `GET` | `/hand/actuator-joint-map` | Letra de actuador → ids de articulación que acciona |
| `GET` | `/hand/output-schema` | El JSON Schema que el LLM debe cumplir |

---

## Proveedores y modelos

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/providers` | Proveedores registrados, los locales primero |
| `GET` | `/providers/models` | Catálogo de modelos, filtrable por proveedor |
| `POST` | `/providers/models` | Registrar un modelo manualmente |
| `GET` | `/providers/lm-studio/probe` | Qué tiene cargado LM Studio ahora mismo |
| `POST` | `/providers/lm-studio/sync` | Importar los modelos cargados al catálogo |

`sync` registra los modelos nuevos de forma conservadora —modo JSON activo, JSON
Schema desactivado— porque los runtimes GGUF varían. Sube los indicadores por
modelo cuando lo hayas verificado.

---

## Proyectos

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/projects` | Listar. `include_archived`, `include_deleted` |
| `POST` | `/projects` | Crear; el slug se genera y se desduplica |
| `GET` | `/projects/{id}` | Obtener |
| `PATCH` | `/projects/{id}` | Actualización parcial; auditada con diff por campo |
| `DELETE` | `/projects/{id}` | Borrado **lógico**; no se destruye nada |
| `POST` | `/projects/{id}/restore` | Deshacer un borrado lógico |
| `GET` | `/projects/{id}/stats` | Recuentos, tokens, coste, latencia — agregados en SQL |
| `GET` | `/projects/{id}/audit` | Todo lo ocurrido dentro del proyecto |

```http
POST /api/v1/projects
{
  "name": "Clasificación de agarres en modelos de 7B",
  "research_question": "¿Degrada la cuantización la interpretación de EMG?",
  "tags": ["emg", "cuantizacion"]
}
```

---

## Experimentos

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/experiments` | Listar |
| `POST` | `/experiments` | Crear con condiciones congeladas fijadas |
| `GET` | `/experiments/{id}` | Obtener |
| `GET` | `/experiments/{id}/comparison` | Tabla comparativa entre modelos |
| `GET` | `/experiments/{id}/failure-modes` | Cómo falla cada modelo, por etapa y código |

`comparison` devuelve `comparable: false` cuando las ejecuciones no compartían
todas un mismo `frozen_context_sha256`. La plataforma prefiere informar de «no
comparable» antes que presentar un ranking con aspecto de autoridad construido
sobre condiciones desiguales.

---

## Prompts

Tres artefactos versionados. Editar crea una versión nueva; las filas existentes
no se modifican nunca.

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/prompts/system` | Versiones del system prompt |
| `POST` | `/prompts/system` | Versión nueva |
| `POST` | `/prompts/system/{id}/activate` | Activar |
| `GET` | `/prompts/technical-context` | Versiones del contexto técnico |
| `GET` | `/prompts/technical-context/generated` | Regenerar el canónico desde el modelo de dominio |
| `POST` | `/prompts/technical-context` | Versión nueva |
| `POST` | `/prompts/technical-context/{id}/activate` | Activar |
| `GET` | `/prompts/dynamic-templates` | Plantillas dinámicas |
| `POST` | `/prompts/dynamic-templates` | Plantilla nueva |
| `POST` | `/prompts/preview` | Ensamblar el prompt final **sin gastar un token** |

`preview` devuelve los tres bloques, los mensajes ensamblados, los recuentos de
caracteres y los cinco digests, incluido `frozen_context_sha256`, la clave de
comparabilidad.

---

## EMG

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/emg/format` | El contrato de la matriz: forma, disposición, rango de amplitud, límites |
| `GET` | `/emg/blank` | Una matriz N×8 a cero |
| `POST` | `/emg/parse` | Parsear CSV / TSV / JSON pegado y normalizar |
| `GET` | `/emg/synthetic/gestures` | Gestos sintéticos disponibles |
| `GET` | `/emg/synthetic` | Generar una ventana etiquetada |
| `GET` | `/emg/windows` | Ventanas almacenadas |
| `GET` | `/emg/windows/{id}` | Una ventana |
| `GET` | `/emg/windows/{id}/csv` | Exportar como CSV |

### Parseo

```http
POST /api/v1/emg/parse
{
  "text": "CH0,CH1,...\n-2,-2,-3,-3,0,2,0,0\n...",
  "sample_rate_hz": 1000,
  "normalisation": "full_scale",
  "full_scale": 512
}
```

La respuesta informa de `divisor`, `observed_peak` e `inferred_full_scale`,
porque cómo se normalizaron las amplitudes determina si dos ventanas son
comparables siquiera.

| `normalisation` | Comportamiento |
|---|---|
| `full_scale` | Divide por el rango declarado del conversor. **Por defecto.** |
| `none` | Rechaza cualquier valor fuera de [-1, 1] |
| `peak` | Divide por el máximo de la propia ventana — **rompe la comparabilidad entre ventanas**, y lo dice en `warnings` |

Una matriz transpuesta (8 filas × N columnas) se detecta y se nombra
explícitamente en lugar de aceptarse.

---

## Ejecuciones

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/executions/run` | Ejecutar un experimento, opcionalmente repetido |
| `GET` | `/executions` | Listar, filtrable |
| `GET` | `/executions/{id}` | Una ejecución con validación, métricas y movimiento |
| `GET` | `/executions/{id}/prompt` | El prompt literal que se envió |
| `POST` | `/executions/{id}/replay-movement` | Reemitir una pose validada almacenada |

```http
POST /api/v1/executions/run
{
  "sampling_configuration_id": "…",
  "window": { "samples": [[…]], "source_mode": "manual", "sample_rate_hz": 1000 },
  "handedness": "right",
  "limit_profile": "TABLE_5_V3",
  "repetitions": 5
}
```

Con `repetitions > 1` la respuesta incluye `determinism`: respuestas distintas y
tasa de acuerdo modal. A temperatura 0 con semilla fija, cualquier valor por
debajo de 1.0 significa que el runtime no respeta la semilla.

`replay-movement` solo funciona con ejecuciones que pasaron la validación, así que
no puede resucitar una pose insegura.

---

## Trazabilidad

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/traceability/{execution_id}` | Reconstruir por completo una ejecución pasada |

Devuelve, en una sola respuesta: prompt, modelo, parámetros, estímulo, respuesta,
rendimiento, validación, métricas, movimiento, errores, logs y entradas de
auditoría, además del actor y el origen de la petición.

Devuelve también `reproducible` y, cuando es falso,
`missing_for_reproduction`: exactamente qué piezas faltan. Un registro que solo
*parece* completo es peor que uno que admite un hueco.

---

## Auditoría

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/audit` | Recorrer la traza, filtrable |
| `GET` | `/audit/actions` | El catálogo cerrado de acciones auditables |
| `GET` | `/audit/entity/{tipo}/{id}` | Todo lo ocurrido a una entidad |

Filtros: `action`, `outcome`, `actor_email`, `entity_type`, `entity_id`,
`project_id`, `since`, `until`.

Las entradas son solo-anexado; por diseño no existe un endpoint de escritura.

---

## Exportación

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/export/executions.csv` | CSV listo para análisis |
| `POST` | `/export/executions.jsonl` | JSON delimitado por líneas, en streaming |
| `POST` | `/export/executions.json` | Las mismas filas en JSON |
| `GET` | `/export/columns` | Orden estable de columnas |

```http
POST /api/v1/export/executions.csv
{
  "project_id": "…",
  "since": "2026-07-01T00:00:00Z",
  "only_validated": false,
  "include_prompts": false
}
```

`only_validated` vale **false** por defecto: excluir los fallos sesgaría en
silencio cualquier tasa de éxito calculada después. `include_prompts` e
`include_emg_matrix` también valen false porque multiplican el tamaño del archivo
por unas treinta veces y por mucho más, respectivamente.

---

## WebSockets

### `/ws/simulator`

Canal de solo lectura de movimientos **validados**. Una respuesta rechazada
produce una trama `{"type": "rejected", …}` para que la interfaz explique el
fallo sin mover la mano.

### `/ws/emg/{session_key}`

Ingesta de estímulo en vivo.

```json
{"type": "configure", "sampling_configuration_id": "…", "auto_run": true}
{"session_id": "…", "sequence": 0, "window": {…}, "auto_run": true}
```

Con `auto_run`, cada trama recorre el camino completo de ejecución: mismo
ensamblado de prompt, misma validación, misma persistencia que una corrida
manual. Las ventanas en vivo y manuales llevan valores distintos de `source_mode`
para que nunca se mezclen en silencio en un análisis.

---

## Códigos de estado

| Código | Significado aquí |
|---|---|
| `200` / `201` | Correcto |
| `204` | Eliminado |
| `400` | La petición es coherente pero la configuración no es utilizable |
| `404` | No encontrado |
| `409` | Conflicto con el estado actual (p. ej. restaurar un proyecto no borrado) |
| `422` | El payload falló la validación — vuelve una lista de campos |
| `503` | Una dependencia es inalcanzable (p. ej. LM Studio) |

Que un modelo produzca un comando inválido **no** es un error HTTP. Es una
ejecución correcta con `validation_passed: false`, porque el fallo *es* el
resultado experimental.

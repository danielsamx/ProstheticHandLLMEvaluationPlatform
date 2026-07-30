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
| `GET` | `/hand/output-contract` | El JSON Schema que el LLM debe cumplir |

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

**Cuatro** artefactos versionados. Editar crea una versión nueva; las filas
existentes no se modifican nunca.

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/prompts/system` | Versiones del system prompt |
| `POST` | `/prompts/system` | Versión nueva |
| `POST` | `/prompts/system/{id}/activate` | Activar |
| `GET` | `/prompts/technical-context` | Versiones del contexto técnico |
| `GET` | `/prompts/technical-context/generated` | Regenerar el canónico desde el modelo de dominio |
| `POST` | `/prompts/technical-context` | Versión nueva |
| `POST` | `/prompts/technical-context/{id}/activate` | Activar |
| `GET` | `/prompts/emg-context` | Versiones del conocimiento EMG |
| `GET` | `/prompts/emg-context/generated` | Regenerar el canónico desde el modelo de dominio |
| `POST` | `/prompts/emg-context` | Versión nueva |
| `POST` | `/prompts/emg-context/{id}/activate` | Activar |
| `GET` | `/prompts/dynamic-templates` | Plantillas dinámicas |
| `POST` | `/prompts/dynamic-templates` | Plantilla nueva |
| `POST` | `/prompts/preview` | Ensamblar el prompt final **sin gastar un token** |

El bloque 3 (conocimiento EMG) es un artefacto aparte del bloque 2 a propósito.
"¿Qué puede hacer esta mano?" solo cambia cuando cambia el hardware; "¿la
co-contracción es un STOP o es coactivación fisiológica?" es una posición
metodológica que se revisa muchas veces. Compartir un solo artefacto obligaría a
que cada experimento sobre la segunda pregunta reversionara también la primera, y
los dos efectos no podrían distinguirse.

```http
POST /api/v1/prompts/preview
{
  "window": { "samples": [[…]], "source_mode": "manual", "sample_rate_hz": 1000 },
  "dynamic_content": "matrix",
  "matrix_max_rows": null,
  "limit_profile": "TABLE_5_V3",
  "context_window": 8192
}
```

`preview` devuelve los **cuatro** bloques, los mensajes ensamblados, el
`full_prompt` unido, los recuentos de caracteres, el presupuesto de tokens por
bloque y los seis digests, incluido `frozen_context_sha256`: la clave de
comparabilidad y la clave de deduplicación de las configuraciones de prompt.

Dos campos de la respuesta informan lo que *realmente* se renderizó, no lo que se
pidió: `matrix_rows_sent` y `dynamic_content`. Un tope de filas diezma con paso
entero, así que un tope de 64 sobre 404 filas da 58; devolver la petición como eco
informaría mal del estímulo.

`budget_advice` se expresa en filas, no en tokens: "este contexto admite unas 159
filas" es algo sobre lo que quien llama puede actuar.

---

## Configuraciones de muestreo

Cómo se le pregunta al modelo: los parámetros de decodificación, más el único
interruptor que no es un parámetro de decodificación.

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/configurations` | Listar, las más nuevas primero |
| `POST` | `/configurations` | Crear |
| `GET` | `/configurations/{id}` | Recuperar |
| `PUT` | `/configurations/{id}` | Reemplazar |
| `DELETE` | `/configurations/{id}` | Eliminar |
| `GET` | `/presets` | Presets guardados del laboratorio |

```http
POST /api/v1/configurations
{
  "name": "greedy · sin razonamiento",
  "model_id": "…",
  "temperature": 0.0,
  "top_p": 1.0,
  "max_tokens": 1024,
  "seed": 42,
  "response_format": "json_object",
  "disable_reasoning": true
}
```

**`disable_reasoning` vale `true` por defecto** y es el campo más determinante de
todos para un modelo de razonamiento. Un modelo de clase Qwen3 parte su salida
—desarrollo a `reasoning_content`, respuesta a `content`— y ante una clasificación
difícil con un techo de tokens puede gastar el techo entero deliberando y devolver
`content` vacío. La plataforma registraría entonces un fallo de parseo para un
modelo que seguía pensando.

Cuando vale true se envían **dos** interruptores, porque existen dos convenciones
y los runtimes no coinciden en cuál leen:

| Se envía | Convención | Lo lee |
|---|---|---|
| `chat_template_kwargs: {"enable_thinking": false}` | Qwen3 | La plantilla de chat |
| `reasoning_effort: "none"` | OpenAI | La capa de inferencia del runtime |

Un runtime que no reconozca uno lo ignora, así que enviar ambos no cuesta nada y
cubre las dos familias.

`response_format` acepta `text`, `json_object` y `json_schema`. Una petición
`json_object` se **eleva** a `json_schema` en los runtimes cuya capa compatible con
OpenAI rechaza la forma simple, LM Studio entre ellos. Elevar en vez de degradar a
texto libre es deliberado: un esquema vuelve el JSON malformado *indecodificable*,
y esa garantía vale la pena conservarla.

Los parámetros no soportados se descartan por modelo en lugar de enviarse y ser
rechazados: un runtime que nunca oyó de `top_k` falla toda la petición por él.

---

## EMG

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/emg/format` | El contrato de la matriz: forma, disposición, rango de amplitud, límites |
| `GET` | `/emg/blank` | Una matriz N×8 a cero |
| `POST` | `/emg/parse` | Parsear CSV / TSV / JSON pegado, sin modificar valores |
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
  "ground_truth_gesture": "close"
}
```

**Los valores pasan sin modificarse.** No hay parámetro de normalización, y el
esquema de la petición prohíbe campos desconocidos: nada entre el electrodo y el
prompt reescala nada, así que aquello sobre lo que se juzga al modelo es lo que
produjo el hardware. `observed_peak` vuelve únicamente para que una interfaz pueda
mostrar el rango de la señal; nada en la plataforma actúa sobre él.

Permisivo con los delimitadores y con las etiquetas de cabecera —las herramientas
de adquisición emiten `CH0…CH7` con la misma facilidad que `CH1…CH8`, y una primera
línea solo de etiquetas se omite por su forma y no por coincidir con nombres
concretos—. Estricto con la matriz misma: una matriz transpuesta (8 filas × N
columnas) corrompería toda característica derivada, así que se detecta y se nombra
explícitamente en lugar de aceptarse.

---

## Ejecuciones

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/executions/run` | Ejecutar un experimento, opcionalmente repetido |
| `GET` | `/executions` | Listar, filtrable |
| `GET` | `/executions/stats` | Agregados calculados **en SQL**, no sobre una página cargada |
| `GET` | `/executions/configurations` | Montajes de prompt congelado distintos, con resultados por modelo |
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
  "repetitions": 5,
  "expected_serial_command": "C",
  "dynamic_content": "matrix",
  "matrix_max_rows": null
}
```

`expected_serial_command` es la hoja de respuestas. Se guarda en la ejecución, se
compara contra el comando **normalizado** para que el formato nunca cuente como
respuesta incorrecta, y **nunca se coloca en ningún prompt**. Las ejecuciones sin
comando esperado quedan fuera del denominador de precisión: "no comparado" y
"comparado e incorrecto" son hechos distintos.

Con `repetitions > 1` la respuesta incluye `determinism`: respuestas distintas y
tasa de acuerdo modal. A temperatura 0 con semilla fija, cualquier valor por
debajo de 1.0 significa que el runtime no respeta la semilla.

`replay-movement` solo funciona con ejecuciones que pasaron la validación, así que
no puede resucitar una pose insegura. También escribe una fila `replay` en el
registro de movimientos: movió la mano, así que se registra como cualquier otra
cosa que la haya movido.

### `GET /executions/stats`

Devuelve `comparable: false` cuando las filas coincidentes no compartían todas un
mismo `frozen_context_sha256`, además de `command_labelled` / `command_matched` /
`command_accuracy`. El denominador viaja con la tasa a propósito: 100% de tres
ejecuciones y 100% de trescientas son afirmaciones distintas.

### `GET /executions/configurations`

Una fila por cada combinación distinta de los tres bloques congelados, con clave en
`frozen_context_sha256`. Cada una lleva su etiqueta (`S1.0 · T1.1 · E1.1`), las
tres versiones de bloque, el texto congelado tal como estaba, `first_used_at` /
`last_used_at`, y `by_model`: los resultados desglosados por modelo, porque una
configuración solo es comparable dentro de uno.

---

## Movimiento

Comandos que llegaron al simulador, a la prótesis, o a ambos. Distinto del
historial de ejecuciones: aquel registra qué *respondieron* los modelos, este
registra qué *movió la mano*.

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/movement/send` | Validar un comando escrito y publicarlo al simulador |
| `POST` | `/movement/log/{id}/delivered` | El navegador informando de qué hizo el hardware |
| `GET` | `/movement/log` | El registro, lo más nuevo primero. `limit` ≤ 1000, filtro `source` |

```http
POST /api/v1/movement/send
{
  "serial_command": "A320,B240",
  "handedness": "right",
  "limit_profile": "TABLE_5_V3",
  "notes": "revisando el enlace tras grabar el firmware"
}
```

Un comando escrito pasa por las **mismas siete etapas de validación** que la
respuesta de un modelo, no por un verificador paralelo. Dos definiciones de
"seguro" se irían separando, y la garantía pasaría a ser la que casualmente se
ejecutara. A los topes mecánicos no les importa quién eligió el número. Un comando
rechazado vuelve como `400` con el mensaje del propio validador, que ya nombra el
actuador, el valor y el perfil que lo rechazó.

La respuesta informa de `simulator_clients`: cero significa que el comando se
aceptó y se publicó pero nadie estaba escuchando, que es un desenlace distinto del
rechazo y se informa como tal.

`POST /movement/log/{id}/delivered?transport=serial` es una llamada **aparte**
porque los dos destinos triunfan y fallan de forma independiente: el simulador se
dibuja desde el backend, el hardware se maneja desde el navegador, y el backend no
puede alcanzar un puerto serie. Una sola escritura combinada tendría que adivinar
la mitad que no ve. Pase `error=…` para registrar una escritura fallida.

`GET /movement/log` filtra por `source`: `execution`, `manual` o `replay`. Los tres
responden preguntas distintas —evidencia, una comprobación de la plomería, y
ninguna de las dos— así que contarlos juntos sería incorrecto.

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

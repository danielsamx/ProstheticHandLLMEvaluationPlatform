# Arquitectura

**Idiomas:** [Español](arquitectura.md) · [English](../en/architecture.md)

---

## Recorrido de una petición

```
Panel izquierdo Angular ──POST /executions/run──►  FastAPI
                                                     │
                                                     ├─ resolver configuración y versiones de prompt
                                                     ├─ persistir la ventana EMG (direccionada por contenido)
                                                     ├─ build_prompt() → 3 bloques + 5 digests SHA-256
                                                     ├─ LiteLLM → LM Studio / proveedor alojado
                                                     ├─ validate_response() → 7 etapas
                                                     ├─ compute_metrics()
                                                     ├─ persistir ejecución + validación + métricas + auditoría
                                                     └─ si pasó → SimulatorMovement + difusión WS
                                                                            │
Simulador Three.js  ◄──── /ws/simulator ────────────────────────────────────┘
```

La última línea es la que importa: el simulador está *aguas abajo* de la
validación, nunca en paralelo. Una respuesta rechazada produce una trama
`rejected` que la interfaz muestra *sin* mover la mano.

---

## Capas

| Capa | Paquete | Responsabilidad |
|---|---|---|
| Dominio | `app/domain` | La prótesis, como código. Sin E/S, sin imports de framework. |
| Contratos | `app/schemas` | Modelos Pydantic v2: salida del LLM, EMG, payloads HTTP |
| Prompts | `app/prompts` | Cuatro bloques y ensamblado determinista |
| Validación | `app/validation` | Pipeline de siete etapas, funciones puras sobre cadenas |
| Persistencia | `app/models`, `app/db` | Mapeadores SQLAlchemy 2, sesión asíncrona |
| Servicios | `app/services` | LiteLLM, orquestador, métricas, EMG, auditoría, exportación |
| Transporte | `app/api`, `app/ws` | Routers FastAPI y canales WebSocket |

`app/domain` es la única capa sin dependencias de las demás. Eso es lo que
permite que un mismo conjunto de definiciones alimente a la vez los validadores,
el texto generado del prompt, la respuesta de `/hand/spec` y el rig del frontend.

### Regla de dependencia

```
domain  ←  schemas  ←  prompts / validation  ←  services  ←  api / ws
   ↑                                              ↓
   └──────────────── models / db ─────────────────┘
```

Las flechas apuntan hacia la dependencia. Que `domain` importara de `services`
sería una violación de capas y es lo primero que hay que revisar.

---

## Por qué el contexto técnico se genera

Escribir a mano la descripción del hardware crearía dos fuentes de verdad: la
prosa que lee el modelo y las constantes que aplica el validador. Se separarían,
y la separación sería invisible: al modelo se le contaría un límite y se le
juzgaría contra otro.

`build_technical_context()` renderiza el bloque desde `hand_spec.py`. Cambia un
límite en el dominio y el prompt cambia con él. La interfaz sigue permitiendo la
edición libre —un contexto escrito a mano es una variable experimental
legítima—, pero el botón **Regenerate** restaura siempre el texto canónico, y un
contexto generado queda marcado con `generated_from_domain=True` para que su
procedencia sea consultable.

---

## Por qué las versiones de prompt son inmutables

Una ejecución guarda a la vez la clave foránea a la fila de versión **y** el texto
literal con su digest. La clave foránea da navegabilidad; la copia da
reproducibilidad incluso si la fila se borra después. Editar un prompt en la
interfaz crea una fila nueva en lugar de mutar la existente, así que un resultado
publicado hace seis meses sigue resolviendo exactamente a los bytes que lo
produjeron.

---

## La comparabilidad como propiedad de primera clase

```
frozen_context_sha256 = SHA256(system_prompt ‖ separador ‖ contexto_técnico)
```

Se almacena en cada ejecución y en cada experimento.
`GET /experiments/{id}/comparison` agrupa por modelo y devuelve un booleano
`comparable` que es falso cuando aparece más de un hash distinto en el conjunto.
La plataforma prefiere devolver una tabla marcada como *no comparable* antes que
un ranking con aspecto de autoridad construido sobre condiciones desiguales.

---

## Medición del determinismo

Las repeticiones de una corrida comparten un UUID `repetition_group`. Cada
ejecución guarda un `response_fingerprint`: SHA-256 de la respuesta parseada,
canonicalizada con claves ordenadas y sin espacios. Dentro de un grupo:

```
tasa_de_determinismo = frecuencia de la huella modal / respuestas válidas
```

A temperatura 0 con semilla fija, cualquier valor por debajo de 1.0 es evidencia
de que el runtime no respeta la semilla —algo habitual en backends GGUF locales—
y es justo lo que un investigador de prótesis necesita saber antes de confiar un
modelo a un lazo de control.

---

## Taxonomía de fallos

El fallo se registra dos veces, deliberadamente:

- `validation_issues` — una fila por incidencia, con un `code` estable, para
  análisis (*¿cómo* falla este modelo?)
- `execution_errors` — una fila por error bloqueante, categorizada, para triaje
  (*¿qué se rompió?*)

Agregar por `code` es lo que convierte «el modelo B falla el 30 % de las veces» en
«el modelo B falla porque antepone prosa al JSON», que sí es accionable.

---

## Auditoría y trazabilidad

### Auditoría

`audit_logs` es solo-anexado. Cada entrada guarda el actor (id, correo y rol
capturados en el momento), la acción tomada de un catálogo cerrado, el resultado,
la entidad afectada, un diff a nivel de campo y el origen de la petición.

El catálogo es cerrado a propósito: una columna de acción en texto libre deriva
hacia una docena de grafías del mismo evento y deja de ser agregable.

Escribir en la traza **nunca** rompe la operación que describe. Un fallo al
escribir se registra en nivel error pero no revierte el trabajo del usuario:
negar un experimento por un problema de contabilidad sería un mal intercambio.

### Trazabilidad

`GET /traceability/{id}` reconstruye una ejecución completa en una sola
respuesta, y devuelve además `reproducible` con la lista exacta de piezas que
faltan cuando es falso. Un registro que solo *parece* completo es peor que uno
que admite un hueco.

### Contexto de petición

Un middleware enlaza un `RequestContext` en una `ContextVar` para toda la vida de
la petición. Todo lo de aguas abajo —registro de ejecución, entradas de
auditoría, líneas de log— lee el origen de ahí, así que la procedencia se captura
una vez y de forma consistente en lugar de re-derivarse en cada punto de llamada.

---

## Estado del frontend

`LabStore` es un almacén basado en signals sin ningún estado conversacional. Una
ejecución es una función pura de `(configuración, prompts congelados, ventana
EMG)`. No se arrastra nada entre corridas salvo los presets que el investigador
haya guardado explícitamente.

La aplicación corre en modo zoneless: los signals dirigen todas las vistas, y
mantener el bucle de render de Three.js fuera de la detección de cambios de
Angular evita un tick por frame sobre todo el árbol de componentes.

El arranque usa `Promise.allSettled`, no `Promise.all`: con este último, un solo
endpoint caído rechazaba el lote entero y dejaba vacías todas las listas, de modo
que un endpoint nuevo o inaccesible borraba en silencio el desplegable de
modelos, los proveedores y los cuatro bloques de prompt a la vez.

---

## Seguridad del simulador

Tres barreras independientes, para que ningún fallo aislado mueva la mano
incorrectamente:

1. El backend solo difunde poses que superaron las siete etapas.
2. `HandScene` expone `applyPose()` como única entrada de movimiento: no hay
   orbitadores de pose, ni deslizadores, ni tiradores.
3. `applyPose()` acota cada ángulo contra los límites articulares de
   `/hand/spec` antes de escribir una transformación.

La cámara sí es del usuario. Mover el punto de vista no es mover la prótesis, así
que no cuesta nada en términos de seguridad y hace mucho más fácil inspeccionar
la pose.

---

## EMG en vivo

`/ws/emg/{session_key}` acepta un mensaje `configure` que fija una configuración
de muestreo y después un flujo de tramas `EmgStreamFrame`. Con `auto_run`, cada
trama recorre el camino completo de ejecución: mismo ensamblado de prompt, misma
validación, misma persistencia que una corrida manual. Las ventanas en vivo y
manuales llevan valores distintos de `source_mode` para que nunca se mezclen en
silencio en un análisis.

---

## Puntos de extensión

- **Hardware real** — suscribirse a `/ws/simulator`, abrir Bluetooth SPP contra
  `Handi EPN V3`, reenviar `serial_command` tal cual y marcar
  `dispatched_to_hardware`.
- **Malla fotorrealista** — `HandScene.loadGltf(url)` empareja huesos por id de
  articulación.
- **Proveedor nuevo** — insertar una fila en `llm_providers` con el prefijo de
  LiteLLM.
- **Perfil de límites nuevo** — añadirlo a `LIMIT_PROFILES`; contextos,
  validadores y el desplegable de la interfaz lo siguen automáticamente.

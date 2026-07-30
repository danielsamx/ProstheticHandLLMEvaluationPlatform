# Guía del desarrollador

**Idiomas:** [Español](guia-desarrollador.md) · [English](../en/developer-guide.md)

---

## Estructura

```
backend/
  app/
    domain/        La prótesis, como código. Sin E/S, sin imports de framework.
    schemas/       Contratos Pydantic v2
    prompts/       Cuatro bloques y ensamblado determinista
    validation/    Pipeline de siete etapas, funciones puras sobre cadenas
    models/        Mapeadores SQLAlchemy 2 (21 tablas)
    db/            Motor y factoría de sesiones
    services/      LiteLLM, orquestador, métricas, EMG, auditoría, exportación
    core/          Configuración, logging, contexto de petición, middleware
    api/v1/        Routers FastAPI
    ws/            Canales WebSocket
    seeds/         Seed idempotente
  alembic/         Migraciones
  tests/           189 tests
frontend/
  src/app/
    core/          Modelos tipados, cliente de API, store de signals, sockets
    features/lab/  Configuración de modelo, panel EMG, bloques de prompt, resultados
    features/simulator/  Escena Three.js, rig procedural, piel PBR
docs/              Documentación bilingüe
scripts/           Utilidades de desarrollo y verificación
```

`app/domain` es la única capa sin dependencias de las demás. Eso es lo que
permite que un mismo conjunto de definiciones alimente a la vez los validadores,
el texto generado del prompt, la respuesta de `/hand/spec` y el rig del frontend.

---

## Regla de dependencia

```
domain  ←  schemas  ←  prompts / validation  ←  services  ←  api / ws
   ↑                                              ↓
   └──────────────── models / db ─────────────────┘
```

Las flechas apuntan hacia la dependencia. Que `domain` importara de `services`
sería una violación de capas y es lo primero que hay que mirar en una revisión.

---

## Cómo añadir cosas

### Un perfil de límites nuevo

Un solo sitio:

```python
# app/domain/hand_spec.py
class LimitProfileId(str, Enum):
    WORN_UNIT_V1 = "WORN_UNIT_V1"

LIMIT_PROFILES = {
    LimitProfileId.WORN_UNIT_V1: LimitProfile(
        LimitProfileId.WORN_UNIT_V1,
        "Envolvente medida, unidad n.º 3 tras 400 horas",
        source="Medición en banco 2026-07-12",
        notes="Recorrido reducido por desgaste del varillaje.",
        limits={Actuator.A_PINKY: (0, 520), ...},
    ),
}
```

El contexto técnico, los validadores, el seed y el desplegable de la interfaz lo
siguen automáticamente. Esa es la recompensa de generar el prompt desde el
dominio en lugar de escribirlo a mano.

### Un proveedor nuevo

Inserta una fila en `llm_providers` con el prefijo de LiteLLM. Sin cambios de
código.

### Una etapa de validación nueva

1. Añádela a `ValidationStage` en `app/validation/results.py`.
2. Impleméntala en `validate_response`, en el orden del pipeline.
3. Retorna pronto ante un error: las etapas posteriores asumen que las anteriores
   pasaron.
4. Añade un test para ese rechazo concreto.

Usa `Severity.WARNING` para lo que deba *registrarse* y no *bloquear*. La
heurística de colisión es un aviso porque su gravedad depende de si hay un objeto
en el agarre.

### Una acción auditada nueva

```python
# app/models/audit.py
class AuditAction(str, Enum):
    DATASET_IMPORTED = "dataset.imported"
```

Después llama a `audit_service.record(...)` desde la operación. El catálogo es
cerrado a propósito: las acciones en texto libre derivan hacia una docena de
grafías del mismo evento y dejan de ser agregables.

### Una columna nueva de exportación

Añádela al final de `export_service.BASE_COLUMNS` y rellénala en `_flatten`.
**Añadir, nunca reordenar**: los scripts de análisis indexan por posición.

---

## Tests

```bash
cd backend && python -m pytest tests -q
python -m pytest tests/test_validation.py -q -k range
```

No hace falta base de datos ni framework web: la suite cubre las capas donde un
error llega al hardware o corrompe un experimento, y esas capas son puras.

| Archivo | Cubre |
|---|---|
| `test_domain.py` | Límites mecánicos, gestos, cinemática |
| `test_protocol.py` | Códec serial, la ambigüedad de `C`, ida y vuelta |
| `test_validation.py` | Las siete etapas |
| `test_prompts.py` | Ensamblado, invariantes del contexto congelado |
| `test_emg_matrix.py` | Contrato de la matriz, características, parseo, síntesis |
| `test_real_acquisition.py` | El camino completo sobre una grabación real del laboratorio |
| `test_governance.py` | Diff de auditoría, trazabilidad, exportación |
| `test_imports.py` | Auditoría estática de imports y comportamiento de CORS |

### Dos tests que no son unitarios

`test_imports.py` recorre cada `from app.x import y` interno y comprueba que el
nombre existe. Una constante renombrada con un importador rezagado pasa todos los
tests unitarios y luego falla al arrancar el contenedor, dentro de un worker de
uvicorn. Esto lo detecta en CI.

`test_real_acquisition.py` recorre el camino completo sobre una grabación real,
incluida la trampa de calibración donde el full scale declarado decide si una
ventana con movimiento se lee como reposo.

### Frontend

```bash
python scripts/check_frontend.py    # sin node_modules
cd frontend && npx tsc --noEmit     # comprobación de tipos completa
```

`check_frontend.py` detecta un backtick suelto que cierra antes de tiempo el
template de un componente —el NG1002 de Angular—. Contar backticks para ver si
están balanceados **no** lo detecta: un par de backticks sueltos mantiene el
total par y aun así rompe el decorador.

---

## Convenciones

### Python

Ruff, longitud de línea 100, objetivo 3.13. Anotaciones de tipo completas.
Pydantic v2 en cada contrato de frontera.

Los comentarios explican **por qué**, no qué. `# incrementar contador` sobre
`contador += 1` es ruido; un comentario que explique por qué el contador no debe
reiniciarse en un reintento, no.

### TypeScript

Angular 22, componentes standalone, zoneless. Signals para todo el estado; RxJS
solo en la frontera HTTP. `ChangeDetectionStrategy.OnPush` en todas partes.

`LabStore` no guarda estado conversacional, y no debe adquirirlo. Una ejecución
es una función pura de `(configuración, prompts congelados, ventana EMG)`.

### Crear objetos ORM en una sesión asíncrona

Los objetos **cargados** por una consulta son seguros: sus cargadores eager ya
corrieron. Los objetos **creados** en la sesión no lo son. `session.flush()` los
vuelve persistentes, y sus relaciones pasan a estar *sin cargar* en vez de
vacías, de modo que el siguiente acceso emite un SELECT perezoso fuera del
greenlet y lanza `MissingGreenlet`.

Dos operaciones de apariencia inocente lo disparan:

```python
execution.logs.append(entry)            # añadir lee antes la colección
ExecutionOut.model_validate(execution)  # Pydantic lee cada atributo mapeado
```

Llama a `prime` justo después del flush:

```python
from app.db.relationships import prime

session.add(execution)
await session.flush()
prime(execution)          # todas las relaciones quedan cargadas y vacías
```

`prime` usa `set_committed_value`, que registra el valor como si se hubiera
cargado, saltándose tanto el cargador como la maquinaria de cascada. Un
`obj.rel = None` no es equivalente: funciona con escalares pero no con
colecciones, y en una relación `delete-orphan` sigue consultando el valor
anterior.

`unloaded(instance)` devuelve los nombres de relación que aún provocarían una
carga, que es la forma más rápida de diagnosticar un `MissingGreenlet`.

Relacionado: nunca uses un `onupdate` del lado SQL (`func.now()`). El servidor
calcula el valor durante el UPDATE, SQLAlchemy no puede verlo, así que expira el
atributo y aplaza un refresco —que después se dispara durante la serialización
de la respuesta y falla igual—. `TimestampMixin` usa un callable de Python
precisamente por esto.

### Migraciones

Todo cambio de esquema lleva migración con un `downgrade()` funcional. Si los
datos no se pueden migrar fielmente, bórralos y dilo en el docstring: `0002` hace
exactamente eso, porque un vector de características no determina la forma de
onda de la que salió y rellenarlo fabricaría datos.

---

## Invariantes

Romper cualquiera de estas y la plataforma deja de ser un instrumento de
investigación.

1. **El simulador solo representa poses validadas.** `applyPose` es su única
   entrada de movimiento, y acota contra los límites articulares del backend
   antes de escribir una transformación.
2. **Las versiones de prompt son inmutables.** Editar inserta; nunca actualiza.
3. **El hash del contexto congelado es la clave de comparabilidad.** Una
   comparación entre hashes distintos debe reportarse como no comparable.
4. **El contexto técnico se genera, no se redacta.** Si no, los límites que se le
   cuentan al modelo se desvían de los que aplica el validador.
5. **Los fallos se guardan, no se descartan.** Son las filas más informativas de
   una exportación.
6. **Las entradas de auditoría son solo-anexado.** No existe camino de
   actualización ni de borrado.

---

## Depuración

### Backend

Los logs son JSON estructurado en stdout:

```bash
docker compose logs backend -f | jq 'select(.level == "ERROR")'
docker compose logs backend -f | jq 'select(.request_id == "…")'
```

Cada respuesta lleva `X-Request-ID`; el mismo valor está en la fila de la
ejecución y en sus entradas de auditoría.

### El prompt realmente enviado

```bash
curl localhost:8000/api/v1/executions/{id}/prompt | jq -r .dynamic_prompt
```

Guardado literal, no reconstruido.

### Procedencia completa

```bash
curl localhost:8000/api/v1/traceability/{id} | jq '{reproducible, missing_for_reproduction}'
```

### Frontend

Al ser zoneless, `ng.applyChanges()` en consola no sirve de nada. Lee los signals
en su lugar. La escena Three.js expone `stats()` con fps y número de triángulos.

---

## Notas de rendimiento

Dos costes dominan, y ambos se midieron en lugar de suponerse.

**Texturas de piel.** Tres búferes de 1024×1024 de ruido fractal —unos tres
millones de píxeles, con varias llamadas trigonométricas cada uno, en el hilo
principal—. Alrededor de un segundo. Se generan una vez por sesión y se
comparten; nada en ellas depende de la lateralidad, así que regenerarlas en cada
cambio de mano era desperdicio puro.

**Construcción del rig.** Ambas manos se construyen una vez y se conmutan por
visibilidad. La segunda se precalienta en `requestIdleCallback` para que incluso
el primer cambio sea instantáneo.

Espejar con `scale.x = -1` evitaría el segundo rig, pero invierte todas las
normales y arruina tanto la iluminación como el borde de sombra. En su lugar la
geometría se regenera con la X negada.

---

## Puntos de extensión

| Objetivo | Dónde |
|---|---|
| Hardware real | Suscribirse a `/ws/simulator`, abrir Bluetooth SPP a `Handi EPN V3`, reenviar `serial_command` tal cual |
| Malla fotorrealista | `HandScene.loadGltf(url)`; huesos emparejados por id de articulación |
| Proveedor nuevo | Fila en `llm_providers` |
| Perfil de límites nuevo | `LIMIT_PROFILES` en `hand_spec.py` |
| Métrica nueva | Columna en `execution_metrics`, rellenada en `metrics_service` |
| Formato de exportación nuevo | Función en `export_service`, ruta en `api/v1/governance.py` |

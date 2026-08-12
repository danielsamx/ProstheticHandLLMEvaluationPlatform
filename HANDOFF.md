# Continuación · Prosthetic Hand LLM Evaluation Platform

Pega esto completo al abrir la sesión nueva.

---

Trabajo en `C:\Users\danie\Documents\TIC-LLM`, una plataforma de investigación que
evalúa modelos de lenguaje en una tarea estrecha: convertir EMG de superficie de 8
canales en un comando de control validado para la prótesis **HANDi EPN V3**
(Escuela Politécnica Nacional). Es mi trabajo de titulación.

## Restricciones permanentes

- **No es un chatbot.** Sin conversación, sin memoria. Cada ejecución es un
  experimento independiente.
- Stack: Angular 22 + Signals + Material 3 + TailwindCSS + TypeScript + RxJS +
  Three.js. Python 3.13 + FastAPI + SQLAlchemy 2 + PostgreSQL + Alembic +
  LiteLLM + Pydantic v2.
- **Sin RAG, sin embeddings, sin base vectorial.**
- **LM Studio es el único proveedor.**
- Paleta `#001F3F`, `#D81B60`, `#FFC107`, `#FFFFFF`, `#000000`. **Sin modo oscuro.**
- Documentación bilingüe: `README.md` en inglés, `docs/README.md` y `docs/es/`
  íntegramente en español.
- Persistencia, auditoría, trazabilidad y exportación completas.
- **El LLM no sabe nada de Bluetooth.** Sabe el rol, los comandos, el contexto EMG,
  y da la salida.
- Todas las versiones de bloque de prompt empiezan en **1.0**.

## Estado actual: el flujo cambió

El flujo **antiguo** mandaba la matriz EMG cruda como texto. **Ya no es el flujo.**
El nuevo, que es el único que debe quedar:

```
subo matriz EMG (CSV)
  -> preprocesamiento: notch 60 Hz, pasabanda 20-450 (recortado a Nyquist),
     rectificado, pasabajos 6 Hz  -> envolvente
  -> imagen: 8 trazas apiladas, flexores arriba, extensores abajo,
     escala de amplitud COMPARTIDA
  -> características (RMS, MAV, WL, MIN, MAX, VARIANCE)
  -> los 4 bloques + la imagen se mandan al VLM
  -> respuesta: solo O, C o no_action
```

Un **toggle con/sin preprocesamiento** gobierna **imagen y características a la vez**.

Orden de bloques: **system → EMG (características) → EMG (imagen) → técnico**.
El técnico está reducido: solo apertura y cierre.

## Ya construido y verificado

- `backend/app/domain/envelope.py` — cadena de filtrado
- `backend/app/services/envelope_image.py` — render determinista a PNG
- `backend/app/services/analysis_service.py` — `analyse()`, punto de entrada único
- `backend/app/prompts/image_context.py` — bloque nuevo
- `backend/app/prompts/technical_context.py` — variante `build_technical_context_open_close()`
- `system_prompt.py` y `emg_context.py` reescritos para este flujo (~1.143 tokens congelados)
- `build_prompt()` llama a `analyse()` y arma el orden nuevo
- `PromptPreviewOut` acepta contenido multimodal y devuelve la imagen
- Guardas de autenticación: `authGuard`, `guestGuard`, `adminGuard`
- `backend/tests/test_envelope_and_image.py` — 18 tests
- `backend/tests/test_documentation.py` — verifica docs contra código

## Pendiente

1. **29 tests fallan.** No son un bug: son la especificación del flujo viejo
   (orden `system → technical → emg`, matriz en texto, turno de usuario como
   cadena). Se borran o reescriben junto con el camino viejo.
2. **Borrar `AnalysisMode` y `DynamicContent`** — un solo camino, sin ramas.
3. **Reestructurar el panel izquierdo del laboratorio** en cuatro secciones:
   - Dataset: solo *Import CSV* + gráfico de ondas + toggle de preprocesamiento.
     Fuera pegar matriz, copiar CSV, limpiar, sintético, cap de filas y *Apply*.
   - Modelo: solo proveedor, modelo y *Refresh*. Fuera los ocho parámetros de
     decodificación. El botón de razonamiento se queda.
   - Prompts: los cuatro bloques, la imagen a enviar, el presupuesto.
   - Resultado.
4. **`supports_vision`** en el catálogo de modelos: un modelo sin visión no debe
   ofrecerse.
5. **Migración 0011** (la cadena ya llegó a 0010): modo de análisis, parámetros
   del filtro, digest de la imagen, origen de las características.
6. **Documentación bilingüe** del flujo nuevo, incluida la tesis: deja de ser
   *"¿puede un LLM leer EMG en crudo?"* y pasa a ser *"¿puede un VLM leer una
   envolvente dibujada y decidir apertura o cierre?"*.

## Hallazgos que no conviene volver a descubrir

- **A 200 Hz (Myo) la banda 20-450 Hz no existe**: Nyquist es 100 Hz, la banda real
  es 20-95 Hz. El recorte se registra en los metadatos.
- **El notch de 60 Hz es indispensable**, no cosmético: a 200 Hz la red cae dentro
  de la única banda representable. Contraste ráfaga/reposo medido: **1.20 sin
  notch, 4.94 con notch**. Ecuador es 60 Hz.
- **ZC y SSC son exactamente 0** con características de la envolvente (medido: 0 y 0
  contra 246 y 377 en crudo). El renderizador los omite; el bloque EMG no debe
  pedirlos.
- **La escala de amplitud compartida entre canales es obligatoria.** Escalar cada
  canal a su propio máximo dibuja igual un canal en reposo y uno contrayéndose.
- **matplotlib estampa la fecha en el PNG**: hay que suprimirla o el digest no
  prueba nada.
- **Con `sharey=True` los ejes comparten formateador**: un `set_yticklabels` vacío
  en el último eje los borra en todos.
- **Nada de backticks dentro de un template literal de Angular** (NG1002).
- **No compongas guardas llamando una a otra**: el tipo `GuardResult` incluye
  `RedirectCommand`. Usa un helper compartido.
- **La guarda debe esperar `restore()`**, no leer `authenticated()`: al recargar
  expulsa a usuarios con sesión válida.
- **`.env` gana dos veces**: Compose lo lee para interpolar y lo pasa al contenedor.
- **Los dos contadores de reintento van en cero** (`num_retries` de LiteLLM y
  `max_retries` del cliente OpenAI, que vale 2 por defecto).

## Verificación

```bash
cd backend && python3 -m pytest -q          # litellm falta en sandbox: ignora
                                            # test_tool_calling y test_auth_rbac
cd frontend && node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
python scripts/check_frontend.py
```

**`tsc` sí corre** — `node_modules` está instalado. Compila el frontend antes de
decir que algo está listo; el análisis estático solo no basta.

## Cómo quiero que trabajes

Comentarios y documentación en el código explicando **por qué**, no qué. Verifica
ejecutando, no suponiendo. Si algo no está hecho, dilo — no lo llames terminado.
Respóndeme en español.

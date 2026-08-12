<div align="center">

<img src="../frontend/src/assets/logo.webp" alt="Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas" width="250" height="96">

# Plataforma de Evaluación de LLM para Prótesis de Mano

**HANDi EPN V3 · EMG → comandos de control validados**

[Main README in English](../README.md)

</div>

---

Plataforma de investigación para evaluar modelos de lenguaje en una tarea
estrecha y crítica para la seguridad: **convertir una matriz de EMG de superficie
de 8 canales en un comando de control validado para la prótesis HANDi EPN V3.**

No es un chatbot. Sin conversaciones, sin memoria. Cada ejecución es un
experimento independiente: un prompt congelado, una ventana de EMG, un modelo,
una respuesta JSON, siete etapas de validación, un registro permanente.

```bash
cp .env.example .env
docker compose up --build
```

Interfaz en http://localhost:4200 · API en http://localhost:8000/docs

---

## Índice de documentos

| Documento | Para quién |
|---|---|
| [Visión general](es/README.md) | Todos — qué es la plataforma y por qué está construida así |
| [Manual de usuario](es/manual-usuario.md) | Investigadores que ejecutan experimentos |
| [Instalación y despliegue](es/instalacion.md) | Quien pone el sistema en marcha |
| [Arquitectura](es/arquitectura.md) | Ingenieros que extienden la plataforma |
| [Referencia de la API](es/api.md) | Quien integre con el backend |
| [Base de datos](es/base-de-datos.md) | Analistas que consultan el registro directamente |
| [Guía del desarrollador](es/guia-desarrollador.md) | Quien contribuya al código |
| [Especificación del hardware](es/hardware.md) | La prótesis HANDi EPN V3, como código |

La documentación técnica extensa también existe en inglés en
[`docs/en/`](en/README.md).

---

## Contenido de esta página

- [Cómo funciona una ejecución](#cómo-funciona-una-ejecución)
- [El laboratorio, control por control](#el-laboratorio-control-por-control)
  - [1 · Proveedor y modelo](#1--proveedor-y-modelo)
  - [2 · El razonamiento, y por qué hay que desactivarlo](#2--el-razonamiento-y-por-qué-hay-que-desactivarlo)
  - [3 · Parámetros de decodificación](#3--parámetros-de-decodificación)
  - [4 · Entrada EMG](#4--entrada-emg)
  - [5 · Qué lleva el prompt dinámico](#5--qué-lleva-el-prompt-dinámico)
  - [6 · Comando serial esperado](#6--comando-serial-esperado)
  - [7 · Los cuatro bloques del prompt](#7--los-cuatro-bloques-del-prompt)
- [Por qué el mismo modelo responde distinto en el chat de LM Studio](#por-qué-el-mismo-modelo-responde-distinto-en-el-chat-de-lm-studio)
- [Modo Live](#modo-live)
- [Conectar la prótesis física](#conectar-la-prótesis-física)
- [Probar un comando a mano](#probar-un-comando-a-mano)
- [El registro de movimientos](#el-registro-de-movimientos)
- [Leer el resultado](#leer-el-resultado)
- [El dashboard](#el-dashboard)
- [Configuraciones de prompt](#configuraciones-de-prompt)

---

## Cómo funciona una ejecución

```
Ventana EMG (N × 8 en crudo)
        │
        ▼
  Ensamblado ─── bloque 1 System        ─┐
  del prompt     bloque 2 Technical     ─┤ congelado: idéntico en cada ejecución
                 bloque 3 EMG knowledge ─┘
                 bloque 4 Dynamic ──────── variable: lo único que cambia
        │
        ▼
     El modelo ────► un objeto JSON
        │
        ▼
  parse → schema → protocol → consistency → range → kinematic → safety
        │                                                          │
        │ falla alguna etapa                                       │ pasan todas
        ▼                                                          ▼
   se registra, la mano no se mueve                  simulador (+ prótesis)
```

La separación entre lo *congelado* y lo *variable* es todo el diseño
experimental. Los bloques 1, 2 y 3 son idénticos byte a byte entre ejecuciones, así que cuando
dos modelos difieren, la diferencia es atribuible al modelo y no al prompt. El
bloque 4 es el estímulo.

Los bloques congelados son tres y no uno porque responden a preguntas de distinta
naturaleza y se revisan con distinta frecuencia: cómo comportarse, qué puede
hacer la mano, y cómo leer el EMG. Cada uno puede variarse mientras los otros
dos quedan idénticos, que es la única forma de atribuir un efecto a uno de
ellos.

**Usted nunca escribe el prompt.** El backend lo ensambla. Usted elige qué entra
en él, y puede leer exactamente lo que se va a enviar antes de gastar un token.

---

## El laboratorio, control por control

### 1 · Proveedor y modelo

**Proveedor** está fijado a LM Studio. Todo corre localmente: ningún dato sale
de la máquina, no hay costo por token, y una ejecución puede repetirse dentro de
un año sin depender de un modelo alojado que pudo ser retirado o actualizado en
silencio por debajo.

**Modelo** lista únicamente lo que LM Studio tiene **cargado** en este momento.
Una entrada en el catálogo no es prueba de que un modelo pueda ejecutarse:
ofrecer uno que no está cargado produce un fallo en inferencia que parece un
problema de red y consume muchísimo tiempo de depuración. Pulse **Refresh**
después de cargar un modelo en LM Studio.

La **ventana de contexto** del modelo importa aquí más que su número de
parámetros. LM Studio carga los modelos con un contexto por defecto muy por
debajo de lo que soporta la arquitectura —habitualmente 4096 u 8192— y ese es el
número que decide si su prompt cabe. Una matriz EMG de 404 filas necesita unos
18.000 tokens. Vea [Entrada EMG](#4--entrada-emg).

### 2 · El razonamiento, y por qué hay que desactivarlo

El botón junto a **Refresh** controla el canal de pensamiento del modelo. **Azul
marino relleno = suprimido** (el valor por defecto). **Contorno ámbar =
razonamiento permitido.** El ámbar es el estado que produce resultados confusos,
así que es el que se dibuja para llamar la atención.

Un modelo de razonamiento —cualquiera de la clase Qwen3— parte su respuesta en
dos: el desarrollo va a un campo `reasoning_content` y la respuesta a `content`.
En esta tarea ese arreglo falla de una forma concreta. Se le da al modelo una
clasificación difícil y un techo de tokens; gasta el techo deliberando, y
`content` llega **vacío**. La plataforma registra un fallo de parseo para un
modelo que, en cierto sentido, seguía pensando.

Cuando está suprimido se envían dos interruptores con la petición, porque existen
dos convenciones y los runtimes no coinciden en cuál leen:

| Se envía | Convención | Lo lee |
|---|---|---|
| `chat_template_kwargs: {"enable_thinking": false}` | Qwen3 | La plantilla de chat, antes de que el modelo vea nada |
| `reasoning_effort: "none"` | OpenAI | La capa de inferencia del propio runtime |

Cualquiera de los dos por sí solo deja un hueco. Juntos cubren ambas familias, y
un runtime que no reconozca uno simplemente lo ignora.

La plataforma además **lee el canal de razonamiento como respaldo**: si `content`
viene vacío y `reasoning_content` no, la respuesta se toma de ahí y la ejecución
registra por qué canal llegó. Eso es un rescate, no una solución: una ejecución
cuya respuesta salió por el canal de razonamiento le está diciendo que la
supresión no surtió efecto.

Lo que realmente se pidió queda guardado por ejecución en `reasoning_mode`, de
modo que un resultado nunca puede reatribuirse en silencio a la condición
equivocada.

### 3 · Parámetros de decodificación

Controlan **cómo el modelo elige cada token**. Son la diferencia entre una
medición y una anécdota.

| Control | Qué hace | Por qué está así |
|---|---|---|
| **Temperature** | Aplana o agudiza la distribución de probabilidad antes de muestrear. `0` toma siempre el token más probable. | **Manténgalo en 0.** Esto es una tarea de control, no de redacción: hay una respuesta correcta y ningún valor en la variedad. Por encima de 0, repetir una ejecución puede dar otro comando, lo que vuelve irrepetible cualquier resultado aislado. La lectura se pone ámbar sobre 0 como advertencia. |
| **Top-P** | Muestreo por núcleo: considera solo el conjunto más pequeño de tokens cuya probabilidad suma P. | A temperatura 0 no tiene efecto: la decodificación voraz lo ignora. Se deja en `1.00` para que no interactúe en silencio si usted sube la temperatura. |
| **Top-K** | Considera solo los K tokens más probables. | Deshabilitado salvo que el runtime declare soporte. El mismo razonamiento que Top-P. |
| **Max tokens** | Techo duro para la longitud de la respuesta. | `1024`. La respuesta es un objeto JSON con hasta seis entradas de comando; por debajo de unos 200 se trunca a media llave. **Una respuesta truncada es indistinguible de una malformada en las métricas**, así que un valor muy bajo registra un error de presupuesto como fallo del modelo. El techo es generoso a propósito: no cuesta nada cuando el modelo es breve, y un valor ajustado es lo primero que se rompe si queda el razonamiento encendido. |
| **Seed** | Fija el generador aleatorio del muestreador. | `42`. Junto con temperatura 0 es lo que hace reproducible una ejecución. El determinismo es una propiedad del muestreador —no algo que se le pueda instruir a un modelo— y por eso el prompt ya no lo pide. |
| **Freq. penalty** | Penaliza tokens ya usados, según su frecuencia. | `0`. Está pensado para que la prosa no se repita. Un comando puede repetir legítimamente una letra (`A320,B180`), así que cualquier penalización aquí distorsiona la salida. |
| **Presence penalty** | Penaliza tokens ya usados, sin más. | `0`, por la misma razón. |
| **Response format** | Pide al runtime que restrinja la decodificación. | `json_object`, **elevado a `json_schema`** para LM Studio, que rechaza la forma simple `json_object`. Con un esquema adjunto el runtime **no puede emitir** JSON malformado, lo que elimina el mayor modo de fallo —prosa envolviendo la respuesta— antes de que ocurra en vez de detectarlo después. La elevación es deliberada: degradar a texto libre habría regalado esa garantía en silencio. |

### 4 · Entrada EMG

El estímulo es una matriz: **N filas × 8 columnas**, en crudo, sin procesar.

- **Filas**: pasos de tiempo en orden ascendente.
- **Columnas**: `CH1…CH8`, en ese orden.
- **Valores**: salida del conversor tal cual. Sin filtrado, sin rectificación,
  sin normalización, sin escalado.

El mapa de canales es anatómico, y es la razón por la que un modelo puede decir
algo sobre la intención:

| Canal | Músculo | Grupo |
|---|---|---|
| CH1 | Flexor digitorum superficialis | flexor |
| CH2 | Flexor carpi radialis | flexor |
| CH3 | Flexor carpi ulnaris | flexor |
| CH4 | Palmaris longus | flexor |
| CH5 | Extensor digitorum communis | extensor |
| CH6 | Extensor carpi radialis longus | extensor |
| CH7 | Extensor carpi ulnaris | extensor |
| CH8 | Brachioradialis | referencia |

La cantidad decisiva es el **balance entre grupos**, nunca un número absoluto.
La ganancia, la colocación de electrodos y el sujeto desplazan la escala
absoluta; la razón sobrevive a las tres:

```
flexor_ratio = RMS flexor / (RMS flexor + RMS extensor)

  > 0.65   domina el grupo volar    → cierre / agarre
  < 0.35   domina el grupo dorsal   → apertura / extensión
  ≈ 0.50   ambos fuertes            → co-contracción, normalmente un STOP deliberado
  todos los canales cerca del piso  → reposo, sin acción
```

**Cuatro acciones, cada una un cuarto de la fila:**

- **Paste matrix** — filas pegadas directamente: CSV, TSV, espacios o JSON.
- **Import CSV** — su archivo de adquisición. Se detecta y omite una fila de
  cabecera (`CH0…CH7` o `CH1…CH8`); se elimina el BOM UTF-8.
- **Copy CSV** — la ventana cargada de vuelta hacia fuera, para el cuaderno de
  laboratorio o una segunda herramienta.
- **Clear** — descarta la ventana.

El selector de ventana sintética estaba antes en primer lugar de esta fila.
Cargaba señales generadas con respuesta conocida, útil para probar la plataforma
pero que no es adquisición, y estando primero se leía como la vía principal de
entrada. **Una ejecución contra EMG sintetizado no es evidencia sobre un modelo.**
El generador sigue disponible en `GET /api/v1/emg/synthetic` para quien quiera
comprobar la pipeline misma.

**Rows sent** limita cuánta matriz llega al prompt. Déjelo vacío para enviarlo
todo, que es el valor por defecto y la opción honesta. Dos cosas que conviene
saber:

- El límite **diezma con paso uniforme**, no trunca. Un tope de 64 sobre una
  ventana de 404 filas muestra una de cada 7, abarcando todo el movimiento.
  Tomar las primeras 64 filas le mostraría al modelo la línea base previa al
  movimiento y nada más.
- Como el paso es un número entero, un tope de 64 sobre 404 filas da 58 filas,
  no 64. El panel y el registro informan lo que realmente se envió.

Pulse **Apply** para confirmar el número. Un campo numérico dispara en cada
pulsación, así que escribir "128" pediría brevemente 1 fila y luego 12; el botón
le da al valor un momento inequívoco para tomar efecto.

### 5 · Qué lleva el prompt dinámico

Tres opciones mutuamente excluyentes, y una variable experimental de verdad, no
una preferencia de visualización.

| Opción | El modelo recibe | La pregunta que responde |
|---|---|---|
| **Matrix** | Las muestras N × 8 en crudo, nada más | *¿Puede un LLM leer EMG en crudo?* La condición más difícil, y la que esta plataforma existe para medir. |
| **Features** | RMS, MAV, ZC, SSC, WL, mín, máx por canal y la razón flexora | *¿Puede un LLM actuar sobre características extraídas?* Una tarea mucho más fácil: el procesamiento de señal ya está hecho. |
| **Both** | La matriz y después los descriptores | La mayor cantidad de información que se le puede dar al modelo. |

Los tres botones se aplican **al instante**: el bloque dinámico y el presupuesto
de tokens se vuelven a renderizar al pulsarlos, así que usted puede ver lo que
cuesta cada condición antes de comprometer una ejecución.

Los descriptores se calculan siempre sobre la ventana **completa**, incluso
cuando la matriz impresa está limitada: un resumen del extracto describiría algo
que usted nunca eligió analizar.

**El modo Features es además la salida cuando un prompt no cabe.** La tabla de
descriptores tiene tamaño fijo sea cual sea la longitud del registro: una
ventana de 4.000 muestras cuesta lo mismo que una de 32.

### 6 · Comando serial esperado

El comando que un experto del dominio dice que esta ventana *debería* producir.
Opcional.

Es lo que convierte una ejecución de demostración en una medición. Pasar la
validación solo significa que el comando estaba bien formado, en rango y era
seguro: un modelo que responde `O` a todas las ventanas saca **100% en
validación y 0% en control**. Sin una hoja de respuestas, nada en el sistema
puede distinguirlo.

- Se escribe con holgura y se guarda ordenado: `a320, b180` queda `A320,B180`.
- Se compara contra el comando **normalizado**, de modo que el formato nunca
  cuenta como respuesta incorrecta.
- **Nunca se coloca en ningún prompt.** Es la hoja de respuestas.
- Las ejecuciones sin comando esperado quedan fuera del denominador de
  precisión: "no comparado" y "comparado e incorrecto" son hechos distintos.

### 7 · Los cuatro bloques del prompt

| Bloque | Contiene | Editable |
|---|---|---|
| **1 · System** | Rol y disciplina de salida. Sin números, sin EMG. | Sí, versionado |
| **2 · Technical Context** | La mano: actuadores y rangos, gestos preestablecidos, sintaxis de comando, envolvente de seguridad. | Sí, versionado |
| **3 · EMG Knowledge** | El mapa de electrodos y cómo razonar sobre él. | Sí, versionado |
| **4 · Dynamic** | El EMG de esta ejecución. | Solo la plantilla — el contenido se ensambla |

**El bloque 2 no dice nada sobre Bluetooth.** Antes abría su sección de formato
con "Bluetooth protocol / ASCII", que describía un enlace en el que el modelo no
toma parte: no abre el socket, no elige los baudios, no ve el cable. Lo que
necesita es la *sintaxis* del comando —letras mayúsculas, separadas por comas— y
eso es lo que queda. El transporte vive en `app.domain.protocol` y en el enlace
serie del navegador, donde algo puede actuar sobre él.

Los bloques 1, 2 y 3 están **congelados**: los mismos bytes en cada ejecución.
Editar cualquiera crea una versión nueva e inmutable, de modo que los resultados
pasados siguen siendo atribuibles a la redacción exacta que los produjo.

El bloque 3 está separado del 2 a propósito. "¿Qué puede hacer esta mano?" es un
hecho del hardware que solo cambia cuando cambia el hardware; "¿la co-contracción
es un STOP o es coactivación fisiológica?" es una posición metodológica que un
investigador revisará muchas veces. Compartir un solo artefacto obligaría a que
cada experimento sobre la segunda pregunta reversionara también la primera.

El bloque 2 se **genera desde el modelo de dominio**, no se escribe a mano. Cada
número sale de la misma fuente que usan los validadores, así que el prompt nunca
puede prometerle al modelo un rango que la pipeline después rechace.
**Regenerate** lo restaura desde el dominio si una versión editada a mano se ha
desviado.

**Preview · count tokens** ensambla el prompt exacto sin gastar nada. Alterne
entre el bloque dinámico solo y el **prompt completo** —system, context y
dynamic unidos tal como los verá el modelo—. Las cuatro tarjetas desglosan el
presupuesto por bloque; cuando el total no cabe, el consejo nombra un número de
filas sobre el que usted puede actuar, en lugar de un número de tokens sobre el
que no.

---

## Por qué el mismo modelo responde distinto en el chat de LM Studio

Una sospecha recurrente y razonable: pega el prompt en el chat de LM Studio y el
modelo cierra la mano; envía el prompt idéntico por esta plataforma y devuelve
`no_action`. El mismo modelo, los mismos pesos, otra respuesta.

Hay **cuatro** causas independientes, y se acumulan:

| Causa | En el chat | Por la API |
|---|---|---|
| **Razonamiento** | Puede que lo haya apagado en la interfaz del chat | Hay que suprimirlo explícitamente — vea [§2](#2--el-razonamiento-y-por-qué-hay-que-desactivarlo) |
| **Valores de decodificación** | temperature 0.8, top-p 0.95, top-k 40 — un preajuste *creativo* | temperature 0, top-p 1, voraz |
| **Historial de conversación** | Cada turno anterior sigue en el contexto | Nada. Cada ejecución está sola |
| **`response_format`** | No se aplica | Un esquema restringe la decodificación token a token |

Ninguna de las cuatro es un error, y ninguna es la plataforma equivocándose. El
chat es una *condición experimental distinta*: un muestreador más cálido con una
conversación detrás. Si quiere la respuesta del chat, lo honesto es reproducir
aquí las condiciones del chat y registrar que lo hizo.

**Los ajustes de carga son otro eje y no pueden explicar una respuesta
distinta.** El panel de *load* de LM Studio —GPU offload, longitud de contexto,
caché KV— decide qué tan rápido corre el modelo y cuánto prompt cabe. Con GPU
Offload en 0, 765 tokens pueden tardar cuatro minutos. Ese es un problema de
latencia, no de respuesta: los mismos pesos en CPU y en GPU producen los mismos
tokens.

**La longitud de contexto, en cambio, sí cambia lo que el modelo lee.** Si el
contexto de carga es 8192 y su prompt son 17.608 tokens, algo tiene que ceder — y
una matriz truncada en silencio es un estímulo distinto del que usted eligió. Las
tarjetas de presupuesto existen precisamente para detectar esto antes de gastar
una ejecución en ello.

### Timeouts y reintentos

`LLM_REQUEST_TIMEOUT_S` vale **1800** por defecto (30 minutos). No es cautela
sobre la red; es el costo observado de un modelo grande sin GPU offload, donde
unos cientos de tokens pueden tardar minutos. Un timeout calibrado para una API
alojada convierte una ejecución local lenta en un fallo registrado.

**Los dos contadores de reintento están en cero** — el `num_retries` de LiteLLM y
el `max_retries` del cliente OpenAI, que vale 2 por defecto y es fácil pasar por
alto. Un experimento reintentado no es el experimento que usted pidió: gasta en
silencio el triple de tiempo real y registra un solo resultado. Si una ejecución
falla, eso *es* el hallazgo.

Tenga en cuenta que `.env` manda por dos vías: Docker Compose lo lee para
interpolar `${VAR}` *y* lo pasa dentro del contenedor. Un valor viejo ahí le gana
al valor por defecto de la aplicación en ambas direcciones, lo cual conviene
recordar cuando un ajuste parece no tomar efecto.

---

## Modo Live

El interruptor **Manual / Live** cambia el origen de la ventana EMG: de un
archivo que usted cargó a un flujo WebSocket.

**Cómo funciona:** un dispositivo o script se conecta a
`ws://localhost:8000/ws/emg` y empuja tramas. Cada trama es una ventana N × 8
completa, no una muestra suelta: el modelo razona sobre una ventana, así que el
flujo debe entregar una.

**Auto-run** decide qué pasa cuando llega una trama:

- **Apagado** — la trama reemplaza la ventana actual. Usted la inspecciona y
  pulsa Run. Úselo mientras configura.
- **Encendido** — cada trama dispara una ejecución automáticamente. Es la
  condición de lazo cerrado: entra EMG, sale comando, la mano se mueve.

Los chips junto al interruptor muestran el estado de conexión y dos contadores:
tramas recibidas y ejecuciones disparadas. Divergen cuando el modelo es más
lento que el flujo, y ese es el número que le dice si el control en tiempo real
es siquiera plausible en este hardware.

**Antes de encender auto-run**, tenga presente que cada trama cuesta una
inferencia completa. En un modelo local sobre CPU eso son segundos, no
milisegundos. Mida primero la latencia de una ejecución manual.

---

## Conectar la prótesis física

El botón **Connect hand** en la cabecera del simulador abre un enlace con el
dispositivo real. Cuando está abierto, cada comando validado va a **ambos**: la
prótesis y el simulador. Cuando está cerrado, los comandos van solo al
simulador: un experimento nunca queda bloqueado por la ausencia de hardware.

### Por qué Web Serial y no Web Bluetooth

El firmware habla **Bluetooth SPP a 115200 baudios**. SPP es Bluetooth
*Classic*, y la API Web Bluetooth solo alcanza servicios GATT de BLE: no puede
abrir un socket SPP en absoluto. Una implementación construida sobre Web
Bluetooth fallaría contra este hardware por más cuidado que se pusiera.

Lo que sí funciona: **empareje primero la prótesis en su sistema operativo.** El
sistema expone el enlace SPP como un puerto serie virtual, y la API Web Serial
abre ese puerto a los 115200 baudios documentados, 8N1 — coincidiendo
exactamente con la especificación del protocolo.

Existe un camino BLE para firmwares que expongan un servicio Nordic UART en su
lugar. Es una alternativa real, no un plan B.

### Pasos

1. Empareje la HANDi EPN V3 en la configuración Bluetooth de su sistema.
2. Abra la interfaz en **Chrome o Edge de escritorio** — Web Serial es exclusivo
   de Chromium; Firefox y Safari no lo implementan.
3. Pulse **Connect hand** y elija el puerto en el selector del navegador.
4. El botón se pone azul marino y cuenta los comandos enviados.

Pulsarlo de nuevo devuelve la mano a `OPEN` antes de desconectar. La
especificación de seguridad lo exige: dejada en agarre, los tendones quedan
cargados, lo cual es malo para el eslabonamiento impreso y peor para lo que la
mano esté sosteniendo.

### Qué puede y qué no puede llegar a los motores

Solo se transmiten tramas que superaron **las siete etapas de validación**. No
existe ruta de código desde una respuesta cruda del modelo hasta el puerto
serie. El navegador es el último lugar que debería decidir si una postura es
segura, así que no lo decide: lo decide el backend, y el navegador únicamente
retransmite lo que el backend ya aprobó.

El intervalo mínimo de 50 ms entre transmisiones se aplica en el propio enlace.
Un modelo no puede violarlo —no controla la temporización— pero una tanda de
repeticiones o una reconexión sí podrían, y quien lo pagaría es el driver de los
motores.

---

## Probar un comando a mano

La fila **Actuator state** del simulador tiene un campo de texto y un botón
**Test**. Escriba `C`, pulse Test, vea cerrarse la mano.

Esto existe para separar dos fallos que desde fuera se ven idénticos. Cuando una
ejecución no produce movimiento, la causa está en **la respuesta del modelo** o en
**la plomería**: validador, WebSocket, enlace serie, firmware. Todo paso de
diagnóstico que empiece con una inferencia tiene el juicio del modelo de por
medio; escribir un comando resuelve la pregunta en una sola acción sin él.

**No** es un atajo alrededor de la validación. Un comando escrito pasa por las
mismas siete etapas que la respuesta de un modelo. Dos definiciones de "seguro" se
irían separando, y la garantía pasaría a ser la que casualmente se ejecutara — y a
los topes mecánicos no les importa quién eligió el número. Un dedazo en un campo
de texto puede destrozar un motorreductor exactamente igual que un mal modelo.

Las formas aceptadas son las del propio protocolo: un gesto suelto (`C`, `P`, `S`)
o posiciones (`A320,B240`). Las minúsculas se aceptan y se normalizan.

Una sola línea de resultado distingue tres desenlaces que un simple "enviado"
aplanaría:

| Resultado | Significa |
|---|---|
| Un mensaje rosa | Rechazado por validación, con la redacción del propio validador: nombra el actuador, el valor y el perfil que lo rechazó |
| `· no client` | Aceptado y publicado, pero ningún simulador estaba escuchando |
| `· sim` / `· sim + hand` | Entregado, y a qué destinos |

---

## El registro de movimientos

`/logs` — cada comando que movió la mano.

Deliberadamente **no** es la misma lista que el historial de ejecuciones. Aquella
registra qué *respondieron* los modelos; esta registra qué se *transmitió*, y las
dos divergen en ambos sentidos:

- Una postura que se resolvió no es una postura que se entregó. El enlace con la
  prótesis puede estar cerrado, o caerse a mitad de sesión.
- Comandos que ningún modelo produjo —pruebas manuales y reenvíos— mueven la mano
  exactamente igual que la respuesta de un modelo, y de otro modo serían
  movimientos sin ningún registro que los explique.

**Dos columnas de destino, no una bandera de "entregado".** El simulador se dibuja
desde el backend; el hardware se maneja desde el navegador. Cualquiera de los dos
puede llegar mientras el otro no, y esa asimetría es precisamente lo que intenta
diagnosticar quien lee este registro. La entrega a la prótesis la confirma el
navegador en una llamada posterior en vez de asumirse al escribir la fila: un
registro escrito por adelantado reclamaría la entrega de un comando que el enlace
dejó caer.

Filtre por origen, porque los tres tipos responden preguntas distintas:

| Origen | Qué es |
|---|---|
| **Model** | La respuesta de un modelo, tras las siete etapas. Esto es evidencia. |
| **Manual** | Escrito para probar el enlace o la mecánica. No es evidencia sobre un modelo. |
| **Replay** | Un movimiento guardado reenviado. Movió la mano otra vez, así que se registra otra vez. |

Los contadores de cabecera son sobre la página cargada, y así están rotulados.
Llamar total al conteo de una página es como un dashboard empieza a mentir.

---

## Leer el resultado

**Las siete compuertas**, en el orden en que se ejecutan. La primera en rojo es
donde el modelo realmente falló; las siguientes no se alcanzaron, no es que las
pasara.

| Etapa | Qué comprueba |
|---|---|
| **parse** | Que se pudo recuperar un objeto JSON |
| **schema** | Que tiene la forma declarada y no inventa campos |
| **protocol** | Que `serial_command` es un comando existente y bien formado |
| **consistency** | Que el comando concuerda con `intent`, `gesture` y `commands` |
| **range** | Que las posiciones están dentro del perfil de límites activo |
| **kinematic** | Que la postura es físicamente alcanzable |
| **safety** | Exclusividad, número de actuadores, reglas de colisión |

`consistency` existe únicamente porque la respuesta declara su decisión dos
veces. Un `serial_command` de `A320` junto a `intent: "no_action"` es un modelo
que se contradijo, y ejecutar cualquiera de las dos mitades sería ejecutar algo
que nunca decidió de forma coherente.

### `no_action` significa que la mano no se mueve

Conviene decirlo aparte, porque fue un fallo real. Los modelos respondían
`{"intent": "no_action", "serial_command": "S"}` — y `S` es STOP, un comando que
*sí* hace algo.

La causa estaba en el contrato, no en el modelo. `serial_command` era obligatorio
para cualquier intención, así que un modelo que eligiera `no_action` tenía que
poner *algo* ahí, y STOP era el gesto más mencionado del prompt. Llenó el campo
como el esquema le indicaba.

El arreglo fue por los dos lados:

- **El esquema** hace `serial_command` opcional, pero solo para `no_action`.
  Cualquier otra intención sigue exigiéndolo.
- **La pipeline** cortocircuita: una inacción declarada con el comando vacío se
  salta protocol, range, kinematic y safety —no hay nada que comprobar—, registra
  las etapas como completadas, no resuelve postura, y pasa.
- **El bloque 3** lo dice con palabras: *"no_action means the hand does not move.
  It is never S, and never O."* Un modelo al que se le da una regla la sigue; una
  regla simplemente omitida no es una regla.

`no_action` con un comando adjunto sigue siendo un error, y sigue fallando en
`consistency`, con un mensaje que dice qué hacer en su lugar.

**Métricas que conviene entender:**

- **Clean reply** — la respuesta fue JSON puro, sin cercas ni prosa alrededor.
  La medida más nítida de adherencia a las instrucciones.
- **Confidence** y **calibration error** — lo que el modelo afirmó sobre sí
  mismo, y qué tan lejos estaba esa afirmación de la verdad. Un modelo
  equivocado a 0.9 y otro equivocado a 0.3 fallan igual en precisión y muy
  distinto aquí. Para un dispositivo que mueve una mano, el segundo es sobre el
  que se puede construir un umbral de seguridad.
- **Match** — el comando producido frente al comando esperado. ✓, ✗, o – para
  una ejecución que nunca se etiquetó.

---

## El dashboard

El registro completo, agregado en la base de datos y no sobre la página que el
navegador tenga cargada por casualidad.

**Command accuracy** responde "¿fue correcto?", a diferencia de la tasa de
aprobación que responde "¿estaba bien formado y era seguro?". El denominador se
muestra junto a ella: 100% de tres ejecuciones y 100% de trescientas son
afirmaciones distintas.

La columna **Input** muestra qué representación vio cada ejecución (`matrix`,
`features`, `both`) y cuántas filas. Ejecuciones bajo condiciones de entrada
distintas son experimentos distintos; la columna existe para que no se lean como
uno solo.

**Mixed conditions** aparece cuando las filas cargadas no compartían todas un
mismo contexto congelado. La comparación por modelo deja entonces de ser
equivalente, y presentarla como un ranking implicaría algo que los datos no
pueden sostener.

**Export CSV** se descarga desde la API para que el archivo sea idéntico byte a
byte al que la API produce, con todas las ejecuciones —fallos incluidos— y las
condiciones que las produjeron.

---

## Configuraciones de prompt

Cada ejecución apunta a la **combinación distinta de bloques congelados** que la
produjo. Se deduplica al escribir, sobre
`frozen_context_sha256 = SHA256(system ‖ technical ‖ EMG knowledge)`:

- Trescientas ejecuciones bajo un mismo montaje dejan **una** fila de
  configuración.
- Cambie una palabra en un bloque y la siguiente ejecución archiva una **segunda**
  fila.
- Devuélvala a como estaba y se reutiliza la **primera**, actualizando su
  `last_used_at`.

Una configuración lleva la etiqueta que usted ve en la interfaz
(`S1.0 · T1.0 · E1.0`), las tres versiones de bloque, y el texto congelado
completo tal como estaba — para que un resultado siga siendo legible después de que
los bloques hayan avanzado.

Los resultados se desglosan **por modelo**, porque una configuración solo es
comparable dentro de uno. Dos modelos bajo la misma configuración es una
comparación; el mismo modelo bajo dos configuraciones es una comparación. Mezclar
ambas cosas a la vez no responde ninguna de las dos.

Esto es lo que vuelve el archivo interrogable y no solamente grande: *qué
redacción produjo este número* tiene una respuesta que no depende de que alguien
se acuerde.

Los cuatro bloques salen en versión **1.0** y solo avanzan cuando alguien cambia
el texto de forma deliberada. Los números llevaban antes la historia de
desarrollo de la propia plataforma —un system prompt en 6.0.0 antes de haber
corrido un solo experimento—, lo que hacía que la tabla de artefactos se leyera
como si hubieran ocurrido cinco estudios previos. Esa historia pertenece a git.

---

## Política de traducción

Las traducciones son idiomáticas, no literales. Los identificadores técnicos
—nombres de tablas, letras de comando, campos JSON, rutas HTTP— **nunca** se
traducen, porque el lector tiene que poder cotejar el documento con el código y
la base de datos. La prosa que explica *por qué* se tomó una decisión se
reescribe en el idioma destino en lugar de transliterarse.

---

<div align="center">

Escuela Politécnica Nacional · Facultad de Ingeniería de Sistemas

</div>

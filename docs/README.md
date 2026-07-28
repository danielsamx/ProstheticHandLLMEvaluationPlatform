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
  - [2 · Parámetros de decodificación](#2--parámetros-de-decodificación)
  - [3 · Entrada EMG](#3--entrada-emg)
  - [4 · Qué lleva el prompt dinámico](#4--qué-lleva-el-prompt-dinámico)
  - [5 · Comando serial esperado](#5--comando-serial-esperado)
  - [6 · Los tres bloques del prompt](#6--los-tres-bloques-del-prompt)
- [Modo Live](#modo-live)
- [Conectar la prótesis física](#conectar-la-prótesis-física)
- [Leer el resultado](#leer-el-resultado)
- [El dashboard](#el-dashboard)

---

## Cómo funciona una ejecución

```
Ventana EMG (N × 8 en crudo)
        │
        ▼
  Ensamblado del ─── bloque 1 System  ─┐
  prompt            bloque 2 Context  ─┤ congelado: idéntico en cada ejecución
                    bloque 3 Dynamic  ─┘ variable: lo único que cambia
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
experimental. Los bloques 1 y 2 son idénticos byte a byte entre ejecuciones, así
que cuando dos modelos difieren, la diferencia es atribuible al modelo y no al
prompt. El bloque 3 es el estímulo.

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
18.000 tokens. Vea [Entrada EMG](#3--entrada-emg).

### 2 · Parámetros de decodificación

Controlan **cómo el modelo elige cada token**. Son la diferencia entre una
medición y una anécdota.

| Control | Qué hace | Por qué está así |
|---|---|---|
| **Temperature** | Aplana o agudiza la distribución de probabilidad antes de muestrear. `0` toma siempre el token más probable. | **Manténgalo en 0.** Esto es una tarea de control, no de redacción: hay una respuesta correcta y ningún valor en la variedad. Por encima de 0, repetir una ejecución puede dar otro comando, lo que vuelve irrepetible cualquier resultado aislado. La lectura se pone ámbar sobre 0 como advertencia. |
| **Top-P** | Muestreo por núcleo: considera solo el conjunto más pequeño de tokens cuya probabilidad suma P. | A temperatura 0 no tiene efecto: la decodificación voraz lo ignora. Se deja en `1.00` para que no interactúe en silencio si usted sube la temperatura. |
| **Top-K** | Considera solo los K tokens más probables. | Deshabilitado salvo que el runtime declare soporte. El mismo razonamiento que Top-P. |
| **Max tokens** | Techo duro para la longitud de la respuesta. | `320`. La respuesta es un objeto JSON con hasta seis entradas de comando; por debajo de unos 200 se trunca a media llave. **Una respuesta truncada es indistinguible de una malformada en las métricas**, así que un valor muy bajo registra un error de presupuesto como fallo del modelo. |
| **Seed** | Fija el generador aleatorio del muestreador. | `42`. Junto con temperatura 0 es lo que hace reproducible una ejecución. El determinismo es una propiedad del muestreador —no algo que se le pueda instruir a un modelo— y por eso el prompt ya no lo pide. |
| **Freq. penalty** | Penaliza tokens ya usados, según su frecuencia. | `0`. Está pensado para que la prosa no se repita. Un comando puede repetir legítimamente una letra (`A320,B180`), así que cualquier penalización aquí distorsiona la salida. |
| **Presence penalty** | Penaliza tokens ya usados, sin más. | `0`, por la misma razón. |
| **Response format** | Pide al runtime que restrinja la decodificación. | `json_schema`. El esquema de respuesta viaja con la petición, de modo que el runtime **no puede emitir** JSON malformado. Esto elimina el mayor modo de fallo —prosa envolviendo la respuesta— antes de que ocurra, en vez de detectarlo después. LM Studio rechaza `json_object`; la plataforma eleva esa petición automáticamente. |

### 3 · Entrada EMG

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

**Tres maneras de cargar una ventana:**

- **Import CSV** — su archivo de adquisición. Se detecta y omite una fila de
  cabecera (`CH0…CH7` o `CH1…CH8`); se elimina el BOM UTF-8.
- **Paste matrix** — CSV, TSV, espacios o JSON.
- **Load labelled synthetic window** — señales generadas con respuesta correcta
  conocida, para probar la plataforma y no el modelo.

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

### 4 · Qué lleva el prompt dinámico

Tres opciones mutuamente excluyentes, y una variable experimental de verdad, no
una preferencia de visualización.

| Opción | El modelo recibe | La pregunta que responde |
|---|---|---|
| **Matrix** | Las muestras N × 8 en crudo, nada más | *¿Puede un LLM leer EMG en crudo?* La condición más difícil, y la que esta plataforma existe para medir. |
| **Features** | RMS, MAV, ZC, SSC, WL, mín, máx por canal y la razón flexora | *¿Puede un LLM actuar sobre características extraídas?* Una tarea mucho más fácil: el procesamiento de señal ya está hecho. |
| **Both** | La matriz y después los descriptores | La mayor cantidad de información que se le puede dar al modelo. |

Los descriptores se calculan siempre sobre la ventana **completa**, incluso
cuando la matriz impresa está limitada: un resumen del extracto describiría algo
que usted nunca eligió analizar.

**El modo Features es además la salida cuando un prompt no cabe.** La tabla de
descriptores tiene tamaño fijo sea cual sea la longitud del registro: una
ventana de 4.000 muestras cuesta lo mismo que una de 32.

### 5 · Comando serial esperado

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

### 6 · Los tres bloques del prompt

| Bloque | Contiene | Editable |
|---|---|---|
| **1 · System** | Rol y disciplina de salida. Sin números. | Sí, versionado |
| **2 · Technical Context** | La mano: comandos, rangos, acoplamiento, protocolo, seguridad, mapa EMG, esquema de respuesta. | Sí, versionado |
| **3 · Dynamic** | El EMG de esta ejecución. | Solo la plantilla — el contenido se ensambla |

Los bloques 1 y 2 están **congelados**: los mismos bytes en cada ejecución.
Editar cualquiera crea una versión nueva e inmutable, de modo que los resultados
pasados siguen siendo atribuibles a la redacción exacta que los produjo.

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

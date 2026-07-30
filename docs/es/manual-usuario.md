# Manual de usuario

*Prosthetic Hand LLM Evaluation Platform — HANDi EPN V3*

**Idiomas:** [Español](manual-usuario.md) · [English](../en/user-manual.md)

---

## Índice

1. [Para qué sirve el sistema](#1-para-qué-sirve-el-sistema)
2. [Antes de empezar](#2-antes-de-empezar)
3. [Inicio de sesión](#3-inicio-de-sesión)
4. [La pantalla, módulo a módulo](#4-la-pantalla-módulo-a-módulo)
5. [Una ejecución completa, de principio a fin](#5-una-ejecución-completa-de-principio-a-fin)
6. [Proyectos](#6-proyectos)
7. [Elegir modelo](#7-elegir-modelo)
8. [Parámetros de decodificación](#8-parámetros-de-decodificación)
9. [Prompts](#9-prompts)
10. [El estímulo EMG](#10-el-estímulo-emg)
11. [Ejecutar una evaluación](#11-ejecutar-una-evaluación)
12. [Leer los resultados](#12-leer-los-resultados)
13. [Historial y reproducción](#13-historial-y-reproducción)
14. [Configuraciones guardadas](#14-configuraciones-guardadas)
15. [Exportar para análisis](#15-exportar-para-análisis)
16. [Trazabilidad y auditoría](#16-trazabilidad-y-auditoría)
17. [Solución de problemas](#17-solución-de-problemas)
18. [Buenas prácticas](#18-buenas-prácticas)

---

## 1. Para qué sirve el sistema

La plataforma responde a una sola pregunta: **¿qué modelo de lenguaje convierte
señales EMG de superficie en los comandos de control más exactos, más
consistentes y más seguros para una prótesis de mano?**

No es un chatbot. No hay conversación, ni memoria, ni preguntas de seguimiento.
Cada ejecución es un experimento independiente: un prompt congelado, una ventana
EMG, un modelo, una respuesta JSON, siete etapas de validación, un registro
permanente.

El diseño es deliberado. Si el modelo pudiera recordar la pregunta anterior, ya
no podrías atribuir una diferencia de resultados al modelo en sí: podría estar
reaccionando a un contexto que no controlaste.

### Qué produce una ejecución correcta

Un JSON que el firmware de la prótesis podría ejecutar tal cual, por ejemplo:

```json
{
  "intent": "gesture",
  "gesture": "C",
  "serial_command": "C",
  "detected_pattern": "power_grasp",
  "confidence": 0.91
}
```

…que el simulador representa después como una mano cerrándose.

`hand` puede seguir apareciendo y se **ignora**. El EMG de un agarre es la misma
señal la produzca la mano que la produzca, así que pedirle al modelo que nombrara el
lado lo obligaba a adivinar algo que la grabación no puede decirle — y una
adivinanza equivocada echaba a perder una ejecución por lo demás correcta.

Negarse a actuar también es una respuesta válida, y se ve así:

```json
{ "intent": "no_action", "serial_command": "" }
```

**Vacío, no `S`.** `S` es STOP, un comando que sí hace algo.

---

## 2. Antes de empezar

| Requisito | Detalle |
|---|---|
| Navegador | Chrome, Edge, Firefox o Safari, versión actual |
| Pantalla | A partir de 1280 px de ancho se trabaja cómodo; por debajo de 768 px los paneles se apilan |
| Backend | En marcha y accesible — la barra superior muestra el estado |
| Un modelo | Al menos uno, cargado en LM Studio o accesible mediante clave de API |

### Si usas LM Studio

LM Studio es el entorno principal de este proyecto porque mantiene los modelos,
los datos y los resultados en tu propia máquina.

1. Abre LM Studio y carga un modelo.
2. Ve a **Developer → Start Server** (puerto 1234 por defecto).
3. Comprueba que el log lista `http://localhost:1234/v1/models` entre los
   endpoints.
4. En la barra superior de la plataforma, la etiqueta **LM Studio** debe estar en
   ámbar. Si está en rosa, el backend no lo alcanza: ve a
   [Solución de problemas](#17-solución-de-problemas).

---

## 3. Inicio de sesión

Cuando la autenticación está activada, entra con la dirección que te asignó tu
institución. Tu identidad queda asociada a todo lo que hagas —cada ejecución,
cada edición de prompt, cada exportación— porque eso es lo que hace auditable el
registro.

Si la plataforma está desplegada en una única estación de trabajo de confianza,
la autenticación puede estar desactivada. En ese caso las ejecuciones se
registran sin actor, y la traza de auditoría identifica la sesión y la máquina en
lugar de a una persona.

**Cerrar sesión** termina la sesión y es en sí mismo un evento auditado.

---

## 4. La pantalla, módulo a módulo

La ventana está dividida exactamente por la mitad.

```
┌──────────────────────────────────────────────────────────────────┐
│  Logo EPN · FIS   Prosthetic Hand LLM Evaluation Platform   ●●●  │  Barra superior
├───────────────────────────────┬──────────────────────────────────┤
│                               │                                  │
│   LABORATORIO (izquierda)     │   SIMULADOR (derecha)            │
│                               │                                  │
│   ▸ Modelo y decodificación   │   Mano 3D                        │
│   ▸ Entrada EMG · 8 canales   │   Conmutador izquierda/derecha   │
│   ▸ Bloques de prompt         │   Arrastrar rota, rueda hace zoom│
│   ▸ Resultado                 │                                  │
│   ▸ Configuraciones e historial│  Lectura de actuadores A–F      │
│                               │                                  │
│   [ Run Evaluation ]          │                                  │
└───────────────────────────────┴──────────────────────────────────┘
```

### Barra superior

Estado de un vistazo:

| Etiqueta | Significado |
|---|---|
| **6 DOF / 11 POT / 5 FSR** | La especificación de la prótesis que cargó el backend |
| **LM Studio** (ámbar) | Accesible, con N modelos cargados |
| **LM Studio** (rosa) | Inaccesible |
| **sensors** (ámbar) | El canal del simulador está conectado |

### Panel izquierdo — el laboratorio

Cinco secciones plegables. **Modelo y decodificación**, **Entrada EMG** y
**Resultado** vienen abiertas porque son las que tocas en cada ejecución.

### Panel derecho — el simulador

Una mano anatómica generada a partir del comando validado.

**Tú controlas la cámara; no controlas la mano.** Arrastra para orbitar, usa la
rueda para el zoom, arrastra con el botón derecho para desplazar, y el botón de
reinicio devuelve la vista por defecto. La pose solo procede de una respuesta del
modelo que superó todas las etapas de validación: no hay ningún control para
mover un dedo a mano, y es a propósito.

---

## 5. Una ejecución completa, de principio a fin

1. **Elige un proyecto** para que la ejecución quede archivada donde la buscarás.
2. **Selecciona proveedor y modelo** en *Modelo y decodificación*, y confirma que el
   botón de razonamiento está en azul marino: suprimido.
3. **Ajusta los parámetros.** Empieza en temperatura 0 con semilla fija.
4. **Carga una ventana EMG**: pega una matriz o importa un CSV.
5. **Elige qué lleva el bloque dinámico** —Matrix, Features o Both— y comprueba en
   las tarjetas de presupuesto que cabe.
6. *(Opcional)* **Escribe el comando serial esperado**, para que la ejecución se
   puntúe y no solo se valide.
7. *(Opcional)* **Previsualiza el prompt** en *Bloques de prompt → 4 · Dynamic*, o el
   prompt completo, para ver exactamente qué recibirá el modelo.
8. **Pulsa Run Evaluation.**
9. **Lee el resultado**: traza de validación, métricas, respuesta cruda.
10. **Mira el simulador**: solo se mueve si la validación pasó.
11. **Repite con otro modelo**, sin cambiar nada más.
12. **Exporta** cuando tengas suficientes ejecuciones para analizar.

---

## 6. Proyectos

Un **proyecto** es el contenedor de una línea de investigación. Un
**experimento** dentro de él fija un conjunto de condiciones congeladas; las
**ejecuciones** son las corridas individuales.

```
Proyecto  "Clasificación de agarres en modelos de 7B"
  └── Experimento  "Límites Tabla 5, mano derecha, temperatura 0"
        ├── Ejecución  qwen2.5-7b   · rep 0
        ├── Ejecución  qwen2.5-7b   · rep 1
        └── Ejecución  llama-3.1-8b · rep 0
```

### Crear uno

`POST /api/v1/projects` con un nombre; el identificador de URL se genera y se
desduplica solo. Anota la **pregunta de investigación**: es el campo que hace
comprensible un proyecto para quien lo lea un año después, tú incluido.

### Archivar y eliminar

Archivar oculta el proyecto de la lista activa. Eliminar es un **borrado lógico**:
la fila se marca, no se destruye nada, y se puede restaurar. Los experimentos que
produjeron resultados publicados siguen siendo reconstruibles para siempre; un
borrado físico rompería justamente la trazabilidad que justifica esta plataforma.

---

## 7. Elegir modelo

### Modelos locales con LM Studio

1. Carga el modelo en LM Studio y arranca su servidor.
2. Pulsa **Import loaded models** en el panel izquierdo.
3. El catálogo se llena con lo que está *realmente cargado*, así que el
   desplegable nunca ofrece un modelo que no existe.

Las entradas nuevas se registran de forma conservadora: modo JSON activo, JSON
Schema desactivado, semilla y top-k disponibles. Sube esos indicadores por modelo
cuando hayas comprobado que el runtime los respeta.

### Modelos alojados

Pon la clave de API del proveedor en `.env` y reinicia el backend. Los modelos
alojados reportan un coste monetario real; los locales reportan cero, y entonces
la medida de eficiencia relevante pasan a ser los tokens por segundo.

### Qué comparar

Comparar un modelo local de 7B contra un modelo alojado de frontera dice poco por
sí solo: difieren en muchas más cosas que una variable. Las comparaciones
informativas son entre modelos de tamaño parecido, o entre configuraciones de un
mismo modelo.

---

## 8. Parámetros de decodificación

| Parámetro | Rango | Notas |
|---|---|---|
| **Temperature** | 0–2 | 0 para reproducibilidad. Por encima, las repeticiones divergen. |
| **Top-P** | 0.01–1 | Déjalo en 1 cuando la temperatura sea 0. |
| **Top-K** | ≥1 | Desactivado salvo que el modelo declare soporte. |
| **Max tokens** | ≥1 | 1024 sobra; la respuesta es un JSON pequeño. |
| **Seed** | entero | Fijarla es lo que hace repetible una ejecución. |
| **Frequency / presence penalty** | −2 a 2 | Déjalos en 0. Penalizar la repetición sobre un esquema JSON fijo perjudica. |
| **Response format** | text / json_object / json_schema | Usa el más estricto que soporte el modelo. |

> **Un control deshabilitado** significa que el catálogo registra que ese modelo
> no lo admite. Enviarlo igualmente haría que se descartara en silencio, y la
> ejecución parecería reproducible sin serlo.

### El botón de razonamiento: no es un parámetro de decodificación

Está junto a **Refresh**, en la fila de proveedor y modelo y no entre los mandos de
arriba, porque es una propiedad de *cómo se le pregunta al modelo* y no de cómo
muestrea.

**Azul marino relleno = razonamiento suprimido** (por defecto). **Contorno ámbar =
razonamiento permitido.** El ámbar es el estado que produce resultados confusos, así
que es el que se dibuja para llamar la atención.

Un modelo de razonamiento —cualquiera de la clase Qwen3— parte su respuesta: el
desarrollo va a un campo `reasoning_content` y la respuesta a `content`. Ante una
clasificación difícil con un techo de tokens, puede gastar el techo deliberando y
dejar `content` **vacío**, y la plataforma registra un fallo de parseo para un modelo
que seguía pensando. Esta es, con diferencia, la razón más común de que una ejecución
"falle" sin motivo visible.

Cuando está suprimido se envían dos interruptores: `enable_thinking: false` (la
convención Qwen3, que lee la plantilla de chat) y `reasoning_effort: "none"` (la
grafía de OpenAI, que lee el runtime). Los runtimes no coinciden en cuál respetan, y
el que no reconozca uno simplemente lo ignora.

Si aun así la respuesta llega por el canal de razonamiento, la plataforma la lee como
respaldo **y registra por qué canal llegó**. Tómalo como señal de que la supresión no
surtió efecto, no como un éxito.

### Repeticiones

Sube **Repetitions** por encima de 1 para correr el experimento idéntico varias
veces. El panel de resultado informa entonces de una **tasa de determinismo**: a
temperatura 0 con semilla fija, cualquier valor por debajo del 100 % significa
que el runtime no respeta la semilla. Conviene saberlo antes de confiar un lazo
de control a ese modelo.

---

## 9. Prompts

Todo prompt enviado a un modelo tiene **cuatro** bloques, ensamblados por el
backend:

```
┌────────────────────────┐
│ 1 · SYSTEM PROMPT      │  congelado — cómo debe comportarse el modelo
├────────────────────────┤
│ 2 · CONTEXTO TÉCNICO   │  congelado — cómo es el hardware
├────────────────────────┤
│ 3 · CONOCIMIENTO EMG   │  congelado — cómo leer la señal
├────────────────────────┤
│ 4 · PROMPT DINÁMICO    │  variable — la ventana EMG
└────────────────────────┘
```

**Tú nunca escribes el prompt final.** El backend lo ensambla antes de cada
inferencia. Esa asimetría es el diseño experimental hecho visible: tú controlas
las constantes, la plataforma controla la variable.

### Bloque 1 — System prompt

Solo comportamiento: responder en JSON, nunca en prosa, no inventar comandos,
negarse antes que adivinar. No contiene cifras, de modo que se versiona
independientemente de la descripción del hardware.

### Bloque 2 — Contexto técnico

La prótesis: actuadores y sus rangos, gestos preestablecidos, sintaxis de comando,
reglas de seguridad. **Se genera desde el código**, no se escribe a mano, para que
los límites que se le cuentan al modelo nunca puedan desviarse de los límites que
aplica el validador.

**Nada sobre Bluetooth.** Antes abría con "Bluetooth protocol / ASCII", describiendo
un enlace en el que el modelo no toma parte: no abre el socket, no elige los
baudios, no ve el cable. Lo que necesita es la *sintaxis* del comando, y eso es lo
que queda.

Se permite editarlo (un contexto escrito a mano es una variable experimental
legítima) y **Regenerate** restaura siempre el texto canónico.

### Bloque 3 — Conocimiento EMG

Cómo leer la señal: el mapa de electrodos, qué descriptores sopesar, y bajo qué
condiciones STOP es la respuesta correcta.

Separado del bloque 2 a propósito. "¿Qué puede hacer esta mano?" solo cambia cuando
cambia el hardware; "¿la co-contracción es un STOP o es coactivación fisiológica?" es
una posición metodológica que revisarás muchas veces. Compartir un solo artefacto
obligaría a que cada experimento sobre la segunda pregunta reversionara también la
primera, y ningún efecto podría atribuirse a ninguna.

Este bloque lleva la corrección que más importó en la práctica. Una versión anterior
decía que una activación flexora y extensora casi igual significaba STOP, lo cual es
falso fisiológicamente —un agarre normal recluta antagonistas para estabilizar la
muñeca— y convertía el agarre corriente en una parada de emergencia. Ahora STOP exige
cuatro condiciones juntas, y la tercera es la que hace el trabajo de verdad:
**descartar antes todo gesto soportado.**

También dice qué significa la inacción: *"no_action means the hand does not move. It
is never S, and never O."* Sin esa línea, los modelos que respondían `no_action`
llenaban el campo de comando con `S` —STOP— porque el esquema exigía un comando y
STOP era el gesto más mencionado del prompt.

### Bloque 4 — Prompt dinámico

Solo lectura, y el único bloque que cambia. Tres botones eligen qué lleva —**Matrix**,
**Features**, **Both**— y se aplican al instante, así que el bloque y el presupuesto
de tokens se vuelven a renderizar al pulsarlos.

**Rows sent** limita cuánta matriz se imprime; pulsa **Apply** para confirmar el
número. El tope diezma con paso uniforme en vez de truncar, así que el modelo ve todo
el movimiento y no la línea base previa. Como el paso es entero, 64 sobre 404 filas da
58, y el panel informa de lo que realmente se envió, no de lo que pediste.

### Leerlo todo junto

**Preview · count tokens** ensambla el prompt exacto sin gastar nada, y puedes
alternar entre el bloque dinámico solo y el **prompt completo**: los cuatro bloques
unidos tal como los verá el modelo.

Las tarjetas de presupuesto desglosan el total por bloque. Cuando no cabe, el consejo
nombra un número de filas sobre el que puedes actuar y no un número de tokens sobre
el que no.

### Versionado

Editar los bloques 1, 2 o 3 crea una **versión nueva**; las existentes no se modifican
nunca. Un resultado publicado hace seis meses sigue resolviendo a los bytes exactos
que lo produjeron. Los cuatro salen en versión **1.0**.

### Configuraciones de prompt

Los tres bloques congelados se resumen juntos en `frozen_context_sha256`, y cada
ejecución apunta a la **configuración distinta** que ese digest identifica. Están
deduplicadas: trescientas ejecuciones bajo un montaje dejan una fila, cambiar un
bloque archiva una segunda, y devolverlo a como estaba reutiliza la primera.

Dos ejecuciones bajo la misma configuración son directamente comparables. Cuando un
conjunto abarca más de una, la plataforma informa **no comparable** en lugar de
presentar un ranking que no puede sostener.

La tabla de configuraciones desglosa los resultados **por modelo**, porque una
configuración solo es comparable dentro de uno.

---

## 10. El estímulo EMG

La entrada es una **matriz de muestras crudas**:

```
N filas (instantes de tiempo, ascendente) × 8 columnas (CH1…CH8)
salida cruda del conversor — nada se filtra, rectifica, normaliza ni escala
```

Lee *a lo ancho* de una fila para un instante; lee *hacia abajo* por una columna
para seguir un electrodo. Una ventana de 200×8 a 1 kHz son 200 ms de señal.

| Columna | Electrodo | Grupo |
|---|---|---|
| CH1–CH4 | Flexores (antebrazo volar) | Cierre |
| CH5–CH7 | Extensores (antebrazo dorsal) | Apertura |
| CH8 | Braquiorradial | Postural |

### Cargarla

**Paste matrix.** Filas pegadas directamente: CSV, TSV, espacios o JSON. La línea de
cabecera se ignora, tanto si dice `CH0…CH7` como `CH1…CH8`.

**Import CSV.** Tu archivo de adquisición. El mismo trato de cabecera; se elimina el
BOM UTF-8.

**Copy CSV / Clear.** La ventana cargada de vuelta hacia fuera, o descartada.

**Streaming en vivo.** Activa **Live acquisition**; el hardware de adquisición
envía ventanas por WebSocket. Con **Auto-run each frame**, cada trama dispara una
ejecución completa.

El selector de ventana sintética estaba antes en primer lugar de esta fila. Generaba
señales con verdad de referencia conocida, útil para probar la plataforma, pero una
ejecución contra EMG sintetizado no es evidencia sobre un modelo — y estando primero
se leía como la vía principal de entrada. El generador sigue disponible en
`GET /api/v1/emg/synthetic` para comprobar la pipeline misma.

### Sin escalado de amplitud — léelo

**Los valores pasan sin modificarse.** No hay ajuste de normalización, ni full scale
declarado, ni divisor. Nada entre el electrodo y el prompt reescala nada.

Es deliberado y es todo el sentido de la medición: aquello sobre lo que se juzga al
modelo es lo que produjo el hardware. Una versión anterior de la plataforma dividía
por un rango de conversor declarado, lo que hacía que cada comparación dependiera de
un número escrito a mano — y uno equivocado volvía incomparables las grabaciones en
silencio mientras todo seguía pareciendo correcto.

La interfaz informa de `observed_peak` para que puedas ver el rango de la señal. Nada
actúa sobre él.

**Lo que sobrevive a la falta de escalado** es la cantidad que siempre fue la correcta
sobre la que razonar: el **balance entre grupos musculares**. La ganancia, la
colocación de electrodos y el sujeto desplazan la escala absoluta; la razón sobrevive
a las tres, y por eso el bloque 3 le dice al modelo que sopese el patrón y no un
umbral aislado.

### Las trazas

Ocho gráficas apiladas: rosa para flexores, navy para extensores, ámbar para el
braquiorradial. La división en tres hace legible de un vistazo el balance
flexor/extensor, que es lo que decide entre abrir y cerrar.

### La tabla de características

Solo lectura. RMS, MAV, cruces por cero, cambios de signo de pendiente, longitud
de onda, mínimo, máximo. **Las deriva el backend de la matriz**, nunca las
aportas tú: de otro modo, una ventana cuyo resumen contradijera su forma de onda
sería indetectable.

---

## 11. Ejecutar una evaluación

Pulsa **Run Evaluation**. El botón está deshabilitado hasta que haya una
configuración seleccionada y la matriz sea válida.

Lo que ocurre:

1. Se ensambla el prompt y se calculan sus hashes.
2. La petición sale hacia el modelo a través de LiteLLM.
3. La respuesta atraviesa siete etapas de validación.
4. Todo se escribe en la base de datos.
5. **Si y solo si la validación pasó**, el simulador recibe la pose.

Una ejecución fallida sigue siendo un registro completo: el prompt, la respuesta,
el motivo del fallo y los tiempos quedan guardados. Los fallos son datos.

---

## 12. Leer los resultados

### El titular

Banda verde con un comando serial, o banda rosa nombrando la etapa que rechazó la
respuesta.

### La traza de validación

Siete segmentos:

```
parse → schema → protocol → consistency → range → kinematic → safety
```

Navy = superada, rosa = la etapa que rechazó, gris = nunca alcanzada.

| Etapa | Rechaza |
|---|---|
| **parse** | No es JSON. Prosa, disculpas, bloques de código. |
| **schema** | Campos ausentes o de más, canal desconocido. `serial_command` puede ir vacío **solo** para `no_action` |
| **protocol** | Trama serial malformada, letra de comando inventada |
| **consistency** | `serial_command` en desacuerdo con los campos estructurados |
| **range** | Una posición fuera de los límites mecánicos |
| **kinematic** | Un ángulo articular fuera de su rango físico |
| **safety** | Exclusividad, velocidad, riesgo de colisión |

Esta es la vista diagnóstica. «El modelo B falla el 30 % de las veces» no es
accionable; «el modelo B falla en `parse` porque antepone una explicación al
JSON» sí lo es.

Una inacción declarada con el comando vacío cortocircuita las cinco últimas etapas
—no hay nada que comprobar— y pasa. Es una respuesta legítima, registrada como
`refused_to_act` y no como un fallo.

### Métricas

Latencia, tokens, coste, rendimiento, intención, patrón detectado, confianza y
—cuando aportaste un comando serial esperado— **Match**: ✓, ✗, o – para una
ejecución que nunca se etiquetó.

Lee **Match** junto a la tasa de aprobación. Pasar la validación solo significa que
el comando estaba bien formado, en rango y era seguro; un modelo que responde `O` a
todas las ventanas saca 100 % en validación y 0 % en control.

### Determinismo

Con repeticiones por encima de 1: cuántas respuestas distintas llegaron y la tasa
de acuerdo modal.

### Respuesta cruda

Desplegable. Vale la pena leerla cuando un modelo falla en `parse`: el problema
suele verse de inmediato.

---

## 13. Historial y reproducción

La sección **Configuraciones e historial** lista las ejecuciones recientes:
modelo, hora, latencia y, o bien el comando serial, o bien la etapa que falló.

**Replay** vuelve a representar un movimiento guardado en el simulador. Solo las
ejecuciones que pasaron la validación tienen movimiento, así que la reproducción
nunca puede resucitar una pose insegura. Un replay se registra igual que cualquier
otra cosa que haya movido la mano.

### Probar un comando a mano

La fila **Actuator state** del simulador tiene un campo de texto y un botón **Test**.
Escribe `C`, pulsa Test, mira cerrarse la mano.

Esto separa dos fallos que desde fuera se ven idénticos. Cuando una ejecución no
produce movimiento, la causa está en la respuesta del modelo o en la plomería:
validador, WebSocket, enlace serie, firmware. Todo diagnóstico que empiece con una
inferencia tiene el juicio del modelo de por medio; escribir un comando lo resuelve
sin él.

**No** es un atajo alrededor de la validación: un comando escrito pasa por las mismas
siete etapas. A los topes mecánicos no les importa quién eligió el número, y un dedazo
en un campo de texto puede destrozar un motorreductor exactamente igual que un mal
modelo.

Un comando rechazado muestra el mensaje del propio validador, que ya nombra el
actuador, el valor y el perfil que lo rechazó. `· no client` significa aceptado pero
sin nadie escuchando: un desenlace distinto del rechazo.

### El registro de movimientos

`/logs` — cada comando que movió la mano, que **no** es la misma lista que el
historial de ejecuciones. Aquel registra qué *respondieron* los modelos; este registra
qué se *transmitió*.

Las dos divergen en ambos sentidos. Una postura que se resolvió no es una postura que
se entregó: el enlace con la prótesis puede estar cerrado o caerse a mitad de sesión.
Y comandos que ningún modelo produjo (pruebas manuales, reenvíos) mueven la mano
exactamente igual que la respuesta de un modelo, y de otro modo serían movimientos sin
ningún registro que los explique.

Dos columnas de destino en vez de una bandera de "entregado", porque el simulador se
dibuja desde el backend mientras el hardware se maneja desde el navegador: cualquiera
de los dos puede llegar mientras el otro no, y esa asimetría es lo que normalmente
intentas diagnosticar.

Filtra por origen: **Model** es evidencia, **Manual** es una comprobación de la
plomería, **Replay** no es ninguna de las dos.

---

## 14. Configuraciones guardadas

El botón de marcador junto a **Run Evaluation** guarda con un nombre el modelo y
los parámetros actuales. Las configuraciones guardadas aparecen en la sección de
historial y se aplican con un clic.

Guarda una configuración **antes** de empezar una comparación y aplica la misma a
todos los modelos. Eso es lo que mantiene honesta la comparación.

---

## 15. Exportar para análisis

`POST /api/v1/export/executions.csv` (también `.jsonl` y `.json`).

Una fila por ejecución con todas las variables ya aplanadas —modelo, parámetros
de decodificación, descriptores del estímulo, resultado, coste, tiempos— de modo
que el archivo entra directo en pandas o R sin ningún join.

```python
import pandas as pd

df = pd.read_csv("executions-20260728-101500.csv")

# Tasa de validación por modelo, solo dentro de un mismo contexto congelado
comparables = df[df.frozen_context_sha256 == df.frozen_context_sha256.mode()[0]]
comparables.groupby("litellm_model").validation_passed.mean().sort_values()
```

Filtra por proyecto, experimento, rango de fechas o modelo. Dos valores por
defecto son deliberados:

- **Los fallos se incluyen.** Excluirlos sesgaría en silencio cualquier tasa de
  éxito que calcules después.
- **Los prompts y las matrices se excluyen.** Multiplican el tamaño del archivo
  por unas treinta veces y por mucho más, respectivamente. Actívalos cuando los
  necesites.

`GET /api/v1/export/columns` devuelve el orden estable de columnas, para que un
script pueda apoyarse en él entre versiones.

---

## 16. Trazabilidad y auditoría

### Reconstruir una ejecución pasada

`GET /api/v1/traceability/{execution_id}` devuelve, en una sola respuesta: qué
prompt, qué modelo, qué parámetros, qué estímulo, qué se obtuvo, cuánto tardó,
cuántos tokens consumió, quién la ejecutó, desde dónde y cuándo.

Devuelve además **`reproducible`** y, cuando es falso, exactamente qué piezas
faltan. Un registro que solo *parece* completo es peor que uno que admite un
hueco.

### La traza de auditoría

`GET /api/v1/audit` — cada proyecto creado, prompt editado, modelo importado,
configuración cambiada, exportación solicitada, sesión abierta o cerrada. Cada
entrada registra el actor, la acción, la fecha y hora, el resultado y un diff a
nivel de campo de lo que cambió.

La traza es **solo-anexado**. Las entradas no se actualizan ni se borran nunca.

`GET /api/v1/audit/entity/{tipo}/{id}` muestra todo lo ocurrido a una entidad.

---

## 17. Solución de problemas

### «LM Studio is not reachable»

| Comprobación | Cómo |
|---|---|
| ¿Está arrancado el servidor? | LM Studio → Developer → Start Server |
| ¿Hay un modelo cargado? | La carga bajo demanda no siempre basta |
| ¿Puerto correcto? | El log debe mostrar `http://localhost:1234/v1/models` |
| ¿Backend en Docker? | Llega a tu máquina por `host.docker.internal`, no por `localhost`. Deja `LM_STUDIO_API_BASE` sin definir en `.env` y se aplica el valor correcto. |

### «Cannot reach the backend»

```bash
docker compose ps            # ¿está levantado?
docker compose logs backend --tail 40
curl http://localhost:8000/health
```

Si la API responde pero el navegador no llega, es CORS. Abrir la interfaz en
`127.0.0.1` o en una dirección de red es un *origen distinto* de `localhost`; en
desarrollo el backend acepta loopback y rangos privados en cualquier puerto.

### El catálogo de modelos está vacío

Recarga la página tras reiniciar el backend. Si sigue vacío, carga un modelo en
LM Studio y pulsa **Import loaded models**.

### Todas las respuestas fallan en `parse`, o la respuesta viene vacía

**Revisa primero el botón de razonamiento.** Un `content` vacío de un modelo de
razonamiento es de lejos la causa más común, y en las métricas se ve exactamente
igual que una respuesta malformada. Suprime el razonamiento y vuelve a ejecutar antes
de cambiar nada más.

Si en cambio la respuesta es prosa envolviendo el JSON:

1. Poner **Response format** en `json_object` o `json_schema`.
2. Bajar la temperatura a 0.
3. Probar un modelo que siga mejor las instrucciones: los modelos pequeños
   cuantizados a menudo no logran suprimir el preámbulo.

La prosa alrededor de la respuesta es un hallazgo legítimo, no solo una molestia: es
el modelo fallando la tarea. Una respuesta vacía de un modelo de razonamiento sin
suprimir no lo es: eso es un problema de configuración, y registrarlo como fallo del
modelo sería incorrecto.

### El modelo responde `no_action` cuando el EMG muestra claramente un movimiento

Tres cosas que comprobar, en este orden:

1. **¿Razonamiento suprimido?** Ver arriba.
2. **¿Cabe el prompt?** Si el contexto de *load* de LM Studio es 8192 y las tarjetas
   de presupuesto dicen 17.608 tokens, la matriz se está truncando y el modelo lee un
   estímulo distinto del que elegiste. Cambia a **Features**, sube el contexto de
   carga, o limita las filas deliberadamente.
3. **¿Lo estás comparando con el chat de LM Studio?** El chat corre a temperatura
   0.8 con top-p 0.95 y tu historial de conversación en contexto. Es una condición
   experimental distinta, no una segunda opinión.

`no_action` acompañado de un comando —`{"intent": "no_action", "serial_command": "S"}`—
es otro asunto y ahora falla en `consistency`. `S` es STOP, que *sí* hace algo; la
inacción significa que el campo va vacío.

### Todas las respuestas fallan en `range`

El modelo emite posiciones fuera de los límites mecánicos. Revisa qué perfil de
límites está activo: el mismo comando puede ser legal bajo `TABLE_5_V3` e ilegal
bajo `ANNEX_A_V3`, porque el manual publica dos envolventes distintas.

### Las repeticiones difieren a temperatura 0

El runtime no respeta la semilla. Es habitual en backends GGUF. Mira en el
registro de la ejecución los **parámetros descartados**: lista exactamente qué
ignoró el runtime.

### La ejecución expira por timeout

`LLM_REQUEST_TIMEOUT_S` vale 1800 segundos por defecto, y es generoso a propósito: un
modelo grande con **GPU Offload en 0** puede tardar minutos en unos cientos de tokens.
Si ves un timeout muy por debajo de esa cifra, un valor viejo en `.env` está pisando
el valor por defecto — Compose lee ese archivo para interpolar *y* lo pasa dentro del
contenedor, así que una línea obsoleta ahí gana dos veces.

Los dos contadores de reintento están en cero por diseño. Un experimento reintentado
en silencio gasta el triple de tiempo real y registra un solo resultado.

### El simulador no se mueve

Primero distingue los dos casos:

- **Con una banda que nombra una etapa** — la validación falló, y es el comportamiento
  correcto. La banda nombra la etapa y el motivo.
- **Sin banda, no pasa nada** — es la plomería, no el modelo. Escribe `C` en el campo
  **Test** de la fila Actuator state. Si la mano se mueve, el transporte está bien y
  el problema está antes; si no, revisa el registro en `/logs` para ver si el comando
  llegó siquiera a constar como publicado.

### El cambio de mano tarda la primera vez

El segundo rig se construye en el primer uso. Los cambios siguientes son
inmediatos.

---

## 18. Buenas prácticas

### Para una comparación defendible

1. **Congela los prompts primero.** No los edites a mitad de una comparación.
2. **Revisa el hash del contexto congelado.** Hashes distintos significan
   ejecuciones incomparables.
3. **Usa las mismas ventanas EMG** en todos los modelos. El checksum lo
   demuestra.
4. **Temperatura 0 y semilla fija**, al menos para empezar.
5. **Repite.** Una sola ejecución de un sistema estocástico no dice casi nada.
6. **Anota el perfil de límites** en tu memoria. Cambia qué cuenta como respuesta
   válida.

### Para un registro fiable

- Escribe la **pregunta de investigación** en el proyecto. Tu yo futuro la
  necesitará.
- **Aporta el comando serial esperado.** Sin hoja de respuestas, un modelo que
  conteste `O` a todas las ventanas saca 100 % en validación y 0 % en control, y nada
  en el registro puede distinguirlo.
- **Mantén el botón de razonamiento en un solo estado** durante una comparación, y
  anota cuál. Cambia por qué canal llega la respuesta, que no es una diferencia
  menor.
- **No borres las ejecuciones fallidas.** Son las filas más informativas del
  archivo.

### Para una evaluación con sentido

- Compara **lo comparable**. Un modelo local de 7B frente a uno alojado de
  frontera difiere en demasiadas variables para atribuir nada.
- Fíjate en **cómo** fallan los modelos, no solo en cuánto.
- Trata una **negativa como un acierto** cuando la entrada es genuinamente
  ambigua. Negarse a mover es más seguro que mover mal, y el system prompt lo
  dice explícitamente.
- Vigila la **calibración**, no solo la exactitud. Un modelo confiadamente
  equivocado es más peligroso en un lazo de control que uno inseguro y acertado.

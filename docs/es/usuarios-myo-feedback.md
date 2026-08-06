# Usuarios, Myo y retroalimentación

## Roles

| Rol | Capacidades |
|---|---|
| Administrador | Todas, incluida administración de cuentas |
| Investigador | Proyectos, prompts, experimentos, Myo, hardware, etiquetas y exportación |
| Pasante | Consulta, ejecución supervisada, captura Myo y valoración de gestos |
| Otro | Consulta de resultados |

La primera cuenta registrada es administrador. Los registros públicos posteriores
reciben siempre el rol `other`; únicamente un administrador puede elevarlos.

## Captura Myo

La vista **Myo** usa Web Bluetooth y las cuatro características EMG del brazalete.
Agrupa muestras de ocho canales a 200 Hz y permite llevar la ventana procesada al
laboratorio. Chrome o Edge y un origen seguro (`https` o `localhost`) son necesarios.

Pipeline `myo-v1`:

1. Reordenamiento configurable de canales.
2. Escala de calibración por canal.
3. Eliminación de componente DC.
4. Notch de 50 o 60 Hz.
5. Pasa banda Butterworth de 20 a 90 Hz para una entrada de 200 Hz.
6. Rectificación opcional y envolvente móvil opcional.
7. Normalización por máximo absoluto, z-score o ninguna.

La API devuelve la ventana cruda y la procesada junto con metadatos del pipeline.
El orden anatómico debe calibrarse para cada colocación del brazalete; no se debe
asumir que los canales Myo coinciden permanentemente con CH1-CH8 del prompt.

## Retroalimentación

Después de un movimiento validado, el investigador marca el gesto como correcto o
incorrecto. Una valoración negativa requiere gesto esperado, observación o evidencia
sensorial. Puede crear hasta tres intentos correctivos por defecto (máximo cinco).

Cada intento es una ejecución nueva con `retry_of_id`, prompt dinámico y hashes propios.
El feedback no modifica el modelo ni los prompts congelados y el resultado corregido no
se transmite automáticamente: debe validarse y confirmarse otra vez.

Las fuentes admitidas son humana, potenciómetros, FSR, visión o combinación. Para una
decisión automática por sensores todavía es necesario que el firmware publique las
lecturas reales; registrar que se escribió el comando no demuestra que el gesto llegó a
la posición objetivo.

import { Injectable, Pipe, PipeTransform, inject, signal } from '@angular/core';

export type AppLanguage = 'en' | 'es';
const ES: Record<string, string> = {
  'Prosthetic hand evaluation platform': 'Plataforma de evaluación de mano protésica',
  'EMG to commands validated by language models': 'EMG a comandos validados por modelos de lenguaje',
  'Laboratory': 'Laboratorio', 'Live Myo': 'Myo en vivo', 'Dataset': 'Dataset', 'Results': 'Resultados', 'Movements': 'Movimientos', 'Simulator': 'Simulador',
  'Configure and run an evaluation': 'Configurar y ejecutar una evaluación', 'Capture and preprocess Myo signals in real time': 'Capturar y preprocesar señales Myo en tiempo real',
  'Build a labelled HANDi EMG dataset': 'Crear un dataset EMG HANDi etiquetado', 'Accumulated evaluation record': 'Registro acumulado de evaluaciones',
  'Commands sent to the simulator or prosthesis': 'Comandos enviados al simulador o la prótesis', 'Manage users': 'Administrar usuarios',
  'Sign out': 'Cerrar sesión', 'Sign in': 'Iniciar sesión', 'No connection': 'Sin conexión', 'models available': 'modelos disponibles',
  'Laboratory access': 'Acceso al laboratorio', 'The first registered account becomes the administrator.': 'La primera cuenta registrada se convierte en administrador.',
  'Full name': 'Nombre completo', 'Institution': 'Institución', 'Email': 'Correo', 'Password': 'Contraseña', 'Register account': 'Registrar cuenta',
  'I already have an account': 'Ya tengo una cuenta', 'Create an account': 'Crear una cuenta', 'Unable to sign in.': 'No fue posible iniciar sesión.',
  'Users and permissions': 'Usuarios y permisos', 'User': 'Usuario', 'Role': 'Rol', 'Permissions': 'Permisos', 'Active': 'Activo',
  'Administrator': 'Administrador', 'Researcher': 'Investigador', 'Intern': 'Pasante', 'Other': 'Otro',
  'Live Myo acquisition': 'Adquisición Myo en tiempo real', 'Status': 'Estado', 'samples': 'muestras', 'Connect Myo': 'Conectar Myo', 'Clear': 'Limpiar',
  'Mains frequency': 'Frecuencia de red', 'Normalisation': 'Normalización', 'Maximum absolute': 'Máximo absoluto', 'None': 'Ninguna',
  'Rectify signal': 'Rectificar señal', 'Preprocess and send to laboratory': 'Preprocesar y enviar al laboratorio',
  'Dataset capture': 'Captura del dataset', 'Session setup': 'Configuración de sesión', 'Session name': 'Nombre de sesión',
  'Subject reference': 'Referencia del sujeto', 'Gestures': 'Gestos', 'Gesture count': 'Cantidad de gestos', 'Samples per gesture': 'Muestras por gesto', 'Rows per sample': 'Filas por muestra',
  'Sample rate': 'Frecuencia de muestreo', 'Select all': 'Seleccionar todos', 'Capture sample': 'Capturar muestra', 'Captured': 'Capturado',
  'Current gesture': 'Gesto actual', 'Next gesture': 'Siguiente gesto', 'Export JSON': 'Exportar JSON', 'Export CSV': 'Exportar CSV',
  'Clear session': 'Limpiar sesión', 'Session complete': 'Sesión completa', 'Connect Myo before capturing.': 'Conecta Myo antes de capturar.',
  'Wait until enough signal rows are available.': 'Espera hasta tener suficientes filas de señal.',
  '1. EMG signal · 8 channels': '1. Señal EMG · 8 canales', '2. Model and parameters': '2. Modelo y parámetros',
  '3. Evaluation prompt': '3. Prompt de evaluación', '4. Result': '4. Resultado', 'Run evaluation': 'Ejecutar evaluación',
  'Running…': 'Ejecutando…', 'Save configuration': 'Guardar configuración', 'View results': 'Ver resultados',
  'Physical gesture outcome': 'Resultado físico del gesto', 'Correct': 'Correcto', 'Incorrect': 'Incorrecto',
  'Rate the real hand, not only the computed command.': 'Valora la mano real, no solo el comando calculado.',
};

@Injectable({ providedIn: 'root' })
export class LanguageService {
  readonly current = signal<AppLanguage>(localStorage.getItem('phlab_language') === 'es' ? 'es' : 'en');
  set(language: AppLanguage): void { this.current.set(language); localStorage.setItem('phlab_language', language); }
  toggle(): void { this.set(this.current() === 'en' ? 'es' : 'en'); }
  text(value: string): string { return this.current() === 'es' ? (ES[value] ?? value) : value; }
}

@Pipe({ name: 'tr', standalone: true, pure: false })
export class TranslatePipe implements PipeTransform {
  private readonly language = inject(LanguageService);
  transform(value: string): string { return this.language.text(value); }
}

import { Routes } from '@angular/router';

/**
 * Three views, deliberately.
 *
 * The laboratory is a working surface: split in half, one experiment at a time,
 * everything needed for the next run visible at once. The dashboard is a
 * reading surface: the accumulated record, full width, nothing to configure.
 * They were competing for the same panel — history is a wide, tabular thing and
 * half a screen was never enough for it.
 *
 * The movement log is a third thing again, and not a section of the dashboard.
 * The dashboard answers "what did the models answer?"; this answers "what
 * actually moved the hand?" — and those are different lists. A pose that
 * resolved is not a pose that was delivered, and the log carries commands no
 * model produced: manual tests and replays, which move the hand exactly as an
 * answer does. Folding them into the execution history would file movements
 * under experiments that never happened.
 */
export const routes: Routes = [
  { path: 'login', title: 'Access · Prosthetic Hand Lab', loadComponent: () => import('@features/auth/login-view').then(m => m.LoginView) },
  { path: 'users', title: 'Users · Prosthetic Hand Lab', loadComponent: () => import('@features/auth/users-view').then(m => m.UsersView) },
  { path: 'myo', title: 'Myo · Prosthetic Hand Lab', loadComponent: () => import('@features/myo/myo-view').then(m => m.MyoView) },
  { path: 'dataset', title: 'Dataset · Prosthetic Hand Lab', loadComponent: () => import('@features/dataset/dataset-view').then(m => m.DatasetView) },
  {
    path: 'lab',
    title: 'Laboratory · Prosthetic Hand LLM Evaluation',
    loadComponent: () => import('@features/lab/lab-view').then((m) => m.LabView),
  },
  {
    path: 'dashboard',
    title: 'Dashboard · Prosthetic Hand LLM Evaluation',
    loadComponent: () =>
      import('@features/dashboard/dashboard-view').then((m) => m.DashboardView),
  },
  {
    path: 'logs',
    title: 'Movement log · Prosthetic Hand LLM Evaluation',
    loadComponent: () =>
      import('@features/logs/movement-log-view').then((m) => m.MovementLogView),
  },
  { path: '', pathMatch: 'full', redirectTo: 'lab' },
  { path: '**', redirectTo: 'lab' },
];

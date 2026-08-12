import { Routes } from '@angular/router';

import { adminGuard, authGuard, guestGuard } from '@core/services/auth.guard';

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
  // The only route reachable without a session, and unreachable with one.
  {
    path: 'login',
    title: 'Access · Prosthetic Hand Lab',
    canActivate: [guestGuard],
    loadComponent: () => import('@features/auth/login-view').then((m) => m.LoginView),
  },

  // Everything else is guarded individually rather than nested under one
  // parent route. A parent would be tidier, but every one of these is lazily
  // loaded, and an unguarded parent downloads the child's bundle before the
  // guard can refuse it — which puts the code for a view on the machine of
  // someone who was never allowed to open it.
  {
    path: 'users',
    title: 'Users · Prosthetic Hand Lab',
    canActivate: [adminGuard],
    loadComponent: () => import('@features/auth/users-view').then((m) => m.UsersView),
  },
  {
    path: 'myo',
    title: 'Myo · Prosthetic Hand Lab',
    canActivate: [authGuard],
    loadComponent: () => import('@features/myo/myo-view').then((m) => m.MyoView),
  },
  {
    path: 'dataset',
    title: 'Dataset · Prosthetic Hand Lab',
    canActivate: [authGuard],
    loadComponent: () => import('@features/dataset/dataset-view').then((m) => m.DatasetView),
  },
  {
    path: 'lab',
    title: 'Laboratory · Prosthetic Hand LLM Evaluation',
    canActivate: [authGuard],
    loadComponent: () => import('@features/lab/lab-view').then((m) => m.LabView),
  },
  {
    path: 'dashboard',
    title: 'Dashboard · Prosthetic Hand LLM Evaluation',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@features/dashboard/dashboard-view').then((m) => m.DashboardView),
  },
  {
    path: 'logs',
    title: 'Movement log · Prosthetic Hand LLM Evaluation',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@features/logs/movement-log-view').then((m) => m.MovementLogView),
  },
  { path: '', pathMatch: 'full', redirectTo: 'lab' },

  // Unknown paths fall to the laboratory, which is itself guarded — so a
  // stranger typing a wrong URL is bounced to the login screen rather than
  // being told which routes exist.
  { path: '**', redirectTo: 'lab' },
];

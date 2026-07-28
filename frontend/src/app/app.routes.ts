import { Routes } from '@angular/router';

/**
 * Two views, deliberately.
 *
 * The laboratory is a working surface: split in half, one experiment at a time,
 * everything needed for the next run visible at once. The dashboard is a
 * reading surface: the accumulated record, full width, nothing to configure.
 * They were competing for the same panel — history is a wide, tabular thing and
 * half a screen was never enough for it.
 */
export const routes: Routes = [
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
  { path: '', pathMatch: 'full', redirectTo: 'lab' },
  { path: '**', redirectTo: 'lab' },
];

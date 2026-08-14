import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { AuthService } from '@core/services/auth.service';
import { LanguageService, TranslatePipe } from '@core/services/language.service';

@Component({
  standalone: true, selector: 'ph-login-view', imports: [FormsModule, MatIconModule, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main class="grid h-full place-items-center bg-ink-50 p-4">
      <form class="w-full max-w-md rounded border border-ink-200 bg-white p-6 shadow-sm" (ngSubmit)="submit()">
        <img
          src="assets/logo-laboratorio-alan-turing.png"
          alt="Escuela Politécnica Nacional y Laboratorio Alan Turing"
          width="1098"
          height="234"
          class="mb-6 h-auto w-full object-contain"
        />
        <h2 class="text-xl font-semibold text-navy">{{ 'Laboratory access' | tr }}</h2>
        <p class="mt-1 text-sm text-ink-500">{{ 'The first registered account becomes the administrator.' | tr }}</p>
        @if (registerMode()) {
          <label class="lab-label mt-5 block">{{ 'Full name' | tr }}</label>
          <input class="mt-1 w-full rounded border p-2" name="name" [(ngModel)]="fullName" required />
          <label class="lab-label mt-3 block">{{ 'Institution' | tr }}</label>
          <input class="mt-1 w-full rounded border p-2" name="institution" [(ngModel)]="institution" />
        }
        <label class="lab-label mt-4 block">{{ 'Email' | tr }}</label>
        <input class="mt-1 w-full rounded border p-2" name="email" type="email" [(ngModel)]="email" required />
        <label class="lab-label mt-3 block">{{ 'Password' | tr }}</label>
        <input class="mt-1 w-full rounded border p-2" name="password" type="password" minlength="10" [(ngModel)]="password" required />
        @if (error()) { <p class="mt-3 text-sm text-pink">{{ error() }}</p> }
        <button class="mt-5 flex w-full items-center justify-center gap-2 rounded bg-navy px-4 py-2 text-white" [disabled]="busy()">
          <mat-icon>{{ registerMode() ? 'person_add' : 'login' }}</mat-icon>
          {{ (registerMode() ? 'Register account' : 'Sign in') | tr }}
        </button>
        <button type="button" class="mt-3 w-full text-sm text-navy underline" (click)="registerMode.set(!registerMode())">
          {{ (registerMode() ? 'I already have an account' : 'Create an account') | tr }}
        </button>
      </form>
    </main>`,
})
export class LoginView {
  private readonly auth = inject(AuthService); private readonly router = inject(Router); private readonly language = inject(LanguageService);
  protected email = ''; protected password = ''; protected fullName = ''; protected institution = '';
  protected readonly registerMode = signal(false); protected readonly busy = signal(false); protected readonly error = signal('');
  protected async submit(): Promise<void> {
    this.busy.set(true); this.error.set('');
    try {
      if (this.registerMode()) await this.auth.register(this.email, this.password, this.fullName, this.institution);
      else await this.auth.login(this.email, this.password);
      await this.router.navigateByUrl('/lab');
    } catch (e: any) { this.error.set(e?.error?.detail ?? this.language.text('Unable to sign in.')); }
    finally { this.busy.set(false); }
  }
}

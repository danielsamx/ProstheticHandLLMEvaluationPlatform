import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';

export type UserRole = 'admin' | 'researcher' | 'intern' | 'other';
export interface AppUser {
  id: string; email: string; full_name: string | null; institution: string | null;
  role: UserRole; is_active: boolean; permissions: string[]; created_at: string;
}
interface TokenResponse { access_token: string; expires_at: string; user: AppUser; }

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly key = 'phlab_access_token';
  readonly user = signal<AppUser | null>(null);
  readonly authenticated = computed(() => !!this.user());
  readonly isAdmin = computed(() => this.user()?.role === 'admin');
  token(): string | null { return localStorage.getItem(this.key); }
  can(permission: string): boolean { return this.user()?.permissions.includes(permission) ?? false; }

  async restore(): Promise<void> {
    if (!this.token()) return;
    try { this.user.set(await firstValueFrom(this.http.get<AppUser>(`${environment.apiBase}/auth/me`))); }
    catch { this.logout(); }
  }
  async login(email: string, password: string): Promise<void> {
    const result = await firstValueFrom(this.http.post<TokenResponse>(`${environment.apiBase}/auth/login`, { email, password }));
    localStorage.setItem(this.key, result.access_token); this.user.set(result.user);
  }
  async register(email: string, password: string, fullName: string, institution?: string): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.apiBase}/auth/register`, {
      email, password, full_name: fullName, institution: institution || null, role: 'other',
    }));
    await this.login(email, password);
  }
  logout(): void { localStorage.removeItem(this.key); this.user.set(null); }
}

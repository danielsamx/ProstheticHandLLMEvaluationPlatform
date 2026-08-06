import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { AppUser, AuthService, UserRole } from '@core/services/auth.service';
import { TranslatePipe } from '@core/services/language.service';

@Component({ standalone: true, selector: 'ph-users-view', imports: [FormsModule, TranslatePipe], changeDetection: ChangeDetectionStrategy.OnPush,
template: `<main class="h-full overflow-auto bg-ink-50 p-6"><div class="mx-auto max-w-5xl">
  <h2 class="text-xl font-semibold text-navy">{{ 'Users and permissions' | tr }}</h2>
  <div class="mt-5 overflow-hidden rounded border border-ink-200 bg-white"><table class="w-full text-left text-sm">
    <thead class="bg-navy text-white"><tr><th class="p-3">{{ 'User' | tr }}</th><th>{{ 'Role' | tr }}</th><th>{{ 'Permissions' | tr }}</th><th>{{ 'Active' | tr }}</th></tr></thead>
    <tbody>@for (user of users(); track user.id) {<tr class="border-t border-ink-200">
      <td class="p-3"><strong>{{ user.full_name }}</strong><br><span class="text-ink-500">{{ user.email }}</span></td>
      <td><select class="rounded border p-2" [(ngModel)]="user.role" (change)="save(user)">
        <option value="admin">{{ 'Administrator' | tr }}</option><option value="researcher">{{ 'Researcher' | tr }}</option>
        <option value="intern">{{ 'Intern' | tr }}</option><option value="other">{{ 'Other' | tr }}</option></select></td>
      <td class="max-w-sm text-xs text-ink-500">{{ user.permissions.join(', ') }}</td>
      <td><input type="checkbox" [(ngModel)]="user.is_active" (change)="save(user)" /></td>
    </tr>}</tbody>
  </table></div>
</div></main>` })
export class UsersView implements OnInit {
  private readonly http = inject(HttpClient); protected readonly auth = inject(AuthService);
  protected readonly users = signal<AppUser[]>([]);
  async ngOnInit(): Promise<void> { this.users.set(await firstValueFrom(this.http.get<AppUser[]>(`${environment.apiBase}/auth/users`))); }
  async save(user: AppUser): Promise<void> {
    const updated = await firstValueFrom(this.http.patch<AppUser>(`${environment.apiBase}/auth/users/${user.id}`, { role: user.role, is_active: user.is_active }));
    this.users.update(rows => rows.map(row => row.id === updated.id ? updated : row));
  }
}

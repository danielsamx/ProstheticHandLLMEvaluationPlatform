import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';

/** A key/value line shown so the user can see what is about to be captured. */
export interface SaveSummaryRow {
  label: string;
  value: string;
}

export interface SaveDialogData {
  title: string;
  hint?: string;
  /** Prefilled name. */
  name: string;
  /** When present the dialog asks for a version tag too. */
  version?: string;
  description?: string;
  /** Whether to offer the "mark as favourite" toggle. */
  offerFavorite?: boolean;
  /** Read-only summary of what is being saved. */
  summary?: SaveSummaryRow[];
  confirmLabel?: string;
}

export interface SaveDialogResult {
  name: string;
  version?: string;
  description?: string;
  isFavorite: boolean;
}

/**
 * Replaces `window.prompt` for saving a named artefact.
 *
 * `prompt()` blocks the whole page, cannot be styled, offers exactly one field
 * and — critically here — shows nothing about what is being saved. A researcher
 * naming a configuration needs to see the parameters it captures, or the saved
 * entry is just a label they will not trust later.
 */
@Component({
  selector: 'ph-save-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, MatButtonModule, MatDialogModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatSlideToggleModule,
  ],
  template: `
    <h2 mat-dialog-title class="!text-base !font-semibold !text-navy">{{ data.title }}</h2>

    <mat-dialog-content class="!pt-1">
      @if (data.hint) {
        <p class="mb-3 text-[12px] leading-relaxed text-ink-500">{{ data.hint }}</p>
      }

      <div class="space-y-1">
        <label class="lab-label">Name</label>
        <mat-form-field appearance="outline" class="dense-field">
          <input matInput
                 [(ngModel)]="name"
                 (keyup.enter)="confirm()"
                 placeholder="A name you will recognise later"
                 cdkFocusInitial />
        </mat-form-field>
        @if (!name.trim()) {
          <p class="text-[11px] text-pink">A name is required.</p>
        }
      </div>

      @if (data.version !== undefined) {
        <div class="mt-3 space-y-1">
          <label class="lab-label">Version tag</label>
          <mat-form-field appearance="outline" class="dense-field">
            <input matInput [(ngModel)]="version" placeholder="1.1.0" />
          </mat-form-field>
          <p class="text-[11px] text-ink-500">
            Existing versions are never modified — this creates a new one, so a
            past result still resolves to the exact text that produced it.
          </p>
        </div>
      }

      <div class="mt-3 space-y-1">
        <label class="lab-label">Description <span class="normal-case text-ink-400">(optional)</span></label>
        <mat-form-field appearance="outline" class="dense-field">
          <textarea matInput rows="2" [(ngModel)]="description"
                    placeholder="Why this configuration, what it is for"></textarea>
        </mat-form-field>
      </div>

      @if (data.summary?.length) {
        <div class="mt-3 overflow-hidden rounded-lg border border-ink-200">
          <div class="border-b border-ink-200 bg-ink-50 px-3 py-1.5">
            <span class="lab-label">This will capture</span>
          </div>
          <dl class="divide-y divide-ink-100">
            @for (row of data.summary; track row.label) {
              <div class="flex items-center justify-between px-3 py-1.5 text-[11px]">
                <dt class="text-ink-500">{{ row.label }}</dt>
                <dd class="lab-mono font-medium text-navy">{{ row.value }}</dd>
              </div>
            }
          </dl>
        </div>
      }

      @if (data.offerFavorite) {
        <div class="mt-3">
          <mat-slide-toggle [(ngModel)]="isFavorite">
            <span class="text-[12px] text-ink-600">Pin to the top of the list</span>
          </mat-slide-toggle>
        </div>
      }
    </mat-dialog-content>

    <mat-dialog-actions align="end" class="!px-6 !pb-4">
      <button mat-stroked-button (click)="cancel()">Cancel</button>
      <button mat-flat-button color="primary" [disabled]="!name.trim()" (click)="confirm()">
        <mat-icon>save</mat-icon>
        {{ data.confirmLabel ?? 'Save' }}
      </button>
    </mat-dialog-actions>
  `,
})
export class SaveDialog {
  protected readonly data = inject<SaveDialogData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<SaveDialog, SaveDialogResult | null>);

  protected name = this.data.name ?? '';
  protected version = this.data.version ?? '';
  protected description = this.data.description ?? '';
  protected isFavorite = false;

  protected confirm(): void {
    if (!this.name.trim()) return;
    this.ref.close({
      name: this.name.trim(),
      version: this.data.version !== undefined ? this.version.trim() || '1.0.0' : undefined,
      description: this.description.trim() || undefined,
      isFavorite: this.isFavorite,
    });
  }

  protected cancel(): void {
    this.ref.close(null);
  }
}

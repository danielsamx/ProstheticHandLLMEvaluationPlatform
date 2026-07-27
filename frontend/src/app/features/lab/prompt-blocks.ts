import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';

/**
 * The three prompt blocks.
 *
 * Blocks 1 and 2 are editable and versioned; block 3 is read-only because the
 * backend assembles it. That asymmetry is the experimental design made visible:
 * the researcher controls the constants, the platform controls the variable.
 */
@Component({
  selector: 'ph-prompt-blocks',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule,
    MatInputModule, MatSelectModule, MatTabsModule, MatTooltipModule,
  ],
  template: `
    <mat-tab-group class="prompt-tabs" [animationDuration]="'120ms'">
      <!-- ── Block 1: System Prompt ──────────────────────────────────────── -->
      <mat-tab>
        <ng-template mat-tab-label>
          <span class="text-[11px]">1 &middot; System</span>
          @if (store.dirtySystemPrompt()) {
            <span class="ml-1 h-1.5 w-1.5 rounded-full bg-amber"></span>
          }
        </ng-template>

        <div class="space-y-2 pt-3">
          <div class="flex items-center gap-2">
            <mat-form-field appearance="outline" class="dense-field !flex-1">
              <mat-select [ngModel]="store.selectedSystemPromptId()"
                          (ngModelChange)="selectSystem($event)">
                @for (v of store.systemPrompts(); track v.id) {
                  <mat-option [value]="v.id">
                    {{ v.name }} &middot; v{{ v.version }}
                    @if (v.is_active) { <span class="text-navy">&nbsp;(active)</span> }
                  </mat-option>
                }
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    [disabled]="!store.dirtySystemPrompt()"
                    (click)="saveSystem()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">save</mat-icon> Save as new version
            </button>
          </div>

          <textarea
            class="lab-mono h-56 w-full resize-none rounded border border-ink-200 bg-ink-50 p-3 text-[11px] leading-relaxed"
            spellcheck="false"
            [ngModel]="store.systemPromptDraft()"
            (ngModelChange)="store.systemPromptDraft.set($event)"></textarea>

          <p class="text-[10px] text-ink-500">
            Behaviour contract only &mdash; no numeric limits. Editing creates a new
            immutable version so past results stay reproducible.
          </p>
        </div>
      </mat-tab>

      <!-- ── Block 2: Technical Context ──────────────────────────────────── -->
      <mat-tab>
        <ng-template mat-tab-label>
          <span class="text-[11px]">2 &middot; Technical Context</span>
          @if (store.dirtyContext()) {
            <span class="ml-1 h-1.5 w-1.5 rounded-full bg-amber"></span>
          }
        </ng-template>

        <div class="space-y-2 pt-3">
          <div class="flex items-center gap-2">
            <mat-form-field appearance="outline" class="dense-field !flex-1">
              <mat-select [ngModel]="store.selectedContextId()"
                          (ngModelChange)="selectContext($event)">
                @for (v of store.technicalContexts(); track v.id) {
                  <mat-option [value]="v.id">
                    {{ v.name }} &middot; v{{ v.version }}
                    @if (v.is_active) { <span class="text-navy">&nbsp;(active)</span> }
                  </mat-option>
                }
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    matTooltip="Regenerate from the domain model, so the text matches the validators exactly."
                    (click)="store.regenerateContextFromDomain()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">autorenew</mat-icon> Regenerate
            </button>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    [disabled]="!store.dirtyContext()"
                    (click)="saveContext()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">save</mat-icon> Save
            </button>
          </div>

          <textarea
            class="lab-mono h-56 w-full resize-none rounded border border-ink-200 bg-ink-50 p-3 text-[11px] leading-relaxed"
            spellcheck="false"
            [ngModel]="store.technicalContextDraft()"
            (ngModelChange)="store.technicalContextDraft.set($event)"></textarea>

          <p class="text-[10px] text-ink-500">
            Structured summary of the four manuals &mdash; commands, ranges, kinematics,
            protocol, safety rules and the output schema. Never a copy of the PDFs.
          </p>
        </div>
      </mat-tab>

      <!-- ── Block 3: Dynamic Prompt (read-only) ─────────────────────────── -->
      <mat-tab>
        <ng-template mat-tab-label><span class="text-[11px]">3 &middot; Dynamic</span></ng-template>

        <div class="space-y-2 pt-3">
          <div class="flex items-center justify-between">
            <span class="text-[10px] uppercase tracking-wider text-ink-500">
              Assembled by the backend &mdash; read only
            </span>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    [disabled]="store.previewLoading()"
                    (click)="store.refreshPreview()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">visibility</mat-icon>
              Preview assembled prompt
            </button>
          </div>

          @if (store.promptPreview(); as preview) {
            <pre class="lab-mono h-48 overflow-auto rounded border border-ink-200 bg-ink-50 p-3 text-[11px] leading-relaxed text-ink-700">{{ preview.dynamic_prompt }}</pre>

            <div class="grid grid-cols-4 gap-2 text-[10px]">
              <div class="rounded border border-ink-200 bg-ink-50 p-2">
                <div class="lab-label">System</div>
                <div class="lab-mono text-ink-700">{{ preview.char_counts['system_prompt'] }} ch</div>
              </div>
              <div class="rounded border border-ink-200 bg-ink-50 p-2">
                <div class="lab-label">Context</div>
                <div class="lab-mono text-ink-700">{{ preview.char_counts['technical_context'] }} ch</div>
              </div>
              <div class="rounded border border-ink-200 bg-ink-50 p-2">
                <div class="lab-label">Dynamic</div>
                <div class="lab-mono text-ink-700">{{ preview.char_counts['dynamic_prompt'] }} ch</div>
              </div>
              <div class="rounded border border-ink-200 bg-ink-50 p-2">
                <div class="lab-label">~Tokens</div>
                <div class="lab-mono text-pink">{{ preview.estimated_prompt_tokens }}</div>
              </div>
            </div>

            <div class="rounded border border-ink-200 bg-ink-50 p-2 text-[10px]">
              <span class="lab-label">Frozen context hash</span>
              <div class="lab-mono break-all text-ink-500">{{ preview.frozen_context_sha256 }}</div>
              <p class="mt-1 text-ink-500">
                Runs sharing this hash saw identical constants, so differences are
                attributable to the model or its decoding parameters.
              </p>
            </div>
          } @else {
            <div class="flex h-48 items-center justify-center rounded border border-dashed border-ink-200 text-[11px] text-ink-500">
              Preview the prompt to see the EMG block exactly as the model will receive it.
            </div>
          }
        </div>
      </mat-tab>
    </mat-tab-group>
  `,
  styles: [`
    :host ::ng-deep .prompt-tabs .mat-mdc-tab-header { border-bottom: 1px solid #22303d; }
    :host ::ng-deep .prompt-tabs .mat-mdc-tab { min-width: 0; padding: 0 12px; }
  `],
})
export class PromptBlocks {
  protected readonly store = inject(LabStore);

  protected selectSystem(id: string): void {
    this.store.selectedSystemPromptId.set(id);
    const version = this.store.systemPrompts().find((p) => p.id === id);
    if (version) this.store.systemPromptDraft.set(version.content);
  }

  protected selectContext(id: string): void {
    this.store.selectedContextId.set(id);
    const version = this.store.technicalContexts().find((p) => p.id === id);
    if (version) {
      this.store.technicalContextDraft.set(version.content);
      if (version.limit_profile) this.store.limitProfile.set(version.limit_profile);
    }
  }

  protected async saveSystem(): Promise<void> {
    const name = prompt('Name for this system prompt version:', 'Custom system prompt');
    if (!name) return;
    const version = prompt('Version tag:', this.nextVersion(this.store.systemPrompts().length));
    if (!version) return;
    await this.store.saveSystemPromptVersion(name, version);
  }

  protected async saveContext(): Promise<void> {
    const name = prompt('Name for this technical context version:', 'Custom technical context');
    if (!name) return;
    const version = prompt('Version tag:', this.nextVersion(this.store.technicalContexts().length));
    if (!version) return;
    await this.store.saveContextVersion(name, version);
  }

  private nextVersion(count: number): string {
    return `1.${count + 1}.0`;
  }
}

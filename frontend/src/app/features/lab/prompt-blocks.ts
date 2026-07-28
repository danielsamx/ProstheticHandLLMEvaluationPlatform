import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { LabStore } from '@core/services/lab.store';
import { SaveDialog, SaveDialogData } from '@shared/save-dialog';
import { firstValueFrom } from 'rxjs';

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

      <!-- ── Block 3: Dynamic Prompt template ────────────────────────────── -->
      <mat-tab>
        <ng-template mat-tab-label>
          <span class="text-[11px]">3 · Dynamic</span>
          @if (store.dirtyTemplate()) {
            <span class="ml-1 h-1.5 w-1.5 rounded-full bg-amber"></span>
          }
        </ng-template>

        <div class="space-y-2 pt-3">
          <div class="flex items-center gap-2">
            <mat-form-field appearance="outline" class="dense-field !flex-1">
              <mat-select [ngModel]="store.selectedTemplateId()"
                          (ngModelChange)="selectTemplate($event)">
                @for (v of store.dynamicTemplates(); track v.id) {
                  <mat-option [value]="v.id">
                    {{ v.name }} · v{{ v.version }}
                    @if (v.is_active) { <span class="text-navy">&nbsp;(active)</span> }
                  </mat-option>
                }
              </mat-select>
            </mat-form-field>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    [disabled]="!store.dirtyTemplate()"
                    (click)="saveTemplate()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">save</mat-icon> Save
            </button>
          </div>

          <textarea
            class="lab-mono h-40 w-full resize-none rounded border border-ink-200 bg-white p-2.5 text-[11px] leading-relaxed"
            spellcheck="false"
            [ngModel]="store.dynamicTemplateDraft()"
            (ngModelChange)="store.dynamicTemplateDraft.set($event)"></textarea>

          <p class="text-[10px] text-ink-500">
            The template, not the content. Placeholders are substituted per run:
            <span class="lab-mono">{{ '{hand}' }}</span>,
            <span class="lab-mono">{{ '{matrix_block}' }}</span>,
            <span class="lab-mono">{{ '{feature_block}' }}</span>,
            <span class="lab-mono">{{ '{sample_count}' }}</span>,
            <span class="lab-mono">{{ '{mean_rms}' }}</span>. Removing one removes
            that information from every prompt.
          </p>

          <div class="flex items-center justify-between border-t border-ink-200 pt-2">
            <span class="lab-label">Assembled preview</span>
            <button mat-stroked-button class="!min-h-0 !py-0 !text-[11px]"
                    [disabled]="store.previewLoading()"
                    (click)="store.refreshPreview()">
              <mat-icon class="!h-4 !w-4 !text-[16px]">visibility</mat-icon>
              Preview · count tokens
            </button>
          </div>

          @if (store.promptPreview(); as preview) {
            <!--
              The dynamic block alone, or everything the model receives.

              "Just this block" is the right default while editing a template,
              but it answers the wrong question when a prompt overflows: the
              overflow is a property of the three blocks together, and reading
              them in three separate places is how the wrong one gets blamed.
            -->
            <div class="flex items-center gap-1 text-[10px]">
              <button class="rounded px-2 py-0.5 font-semibold transition-colors"
                      [class]="fullPrompt() ? 'text-ink-500 hover:text-navy' : 'bg-navy text-white'"
                      (click)="fullPrompt.set(false)">
                Dynamic block
              </button>
              <button class="rounded px-2 py-0.5 font-semibold transition-colors"
                      [class]="fullPrompt() ? 'bg-navy text-white' : 'text-ink-500 hover:text-navy'"
                      (click)="fullPrompt.set(true)">
                Full prompt
              </button>
              <span class="ml-auto text-ink-400">
                {{ preview.dynamic_content }}
                @if (preview.matrix_rows_sent) {
                  · {{ preview.matrix_rows_sent }} of {{ store.sampleCount() }} rows
                }
              </span>
              <button class="ml-2 text-ink-400 hover:text-pink"
                      matTooltip="Copy what is shown"
                      (click)="copy(fullPrompt() ? preview.full_prompt : preview.dynamic_prompt)">
                <mat-icon class="!h-4 !w-4 !text-[16px]">
                  {{ copied() ? 'check' : 'content_copy' }}
                </mat-icon>
              </button>
            </div>

            <pre class="lab-mono overflow-auto rounded border border-ink-200 bg-ink-50 p-2.5 text-[11px] leading-relaxed text-ink-700"
                 [class]="fullPrompt() ? 'h-72' : 'h-40'">{{ fullPrompt() ? preview.full_prompt : preview.dynamic_prompt }}</pre>

            <!--
              The token budget, as four cards.

              Each block gets its own colour so the eye can go straight to the
              one that dominates without reading four numbers first — on a real
              recording the dynamic block is an order of magnitude larger than
              the other two, and that is the whole story of whether a prompt
              fits.
            -->
            <div class="grid grid-cols-4 gap-1.5">
              @for (row of tokenRows(preview); track row.label) {
                <div class="flex items-center gap-1.5 rounded-md px-2 py-1.5"
                     [class]="row.tone"
                     [matTooltip]="row.hint">
                  <mat-icon class="!h-4 !w-4 shrink-0 !text-[16px] opacity-70">
                    {{ row.icon }}
                  </mat-icon>
                  <div class="min-w-0 leading-none">
                    <div class="lab-mono text-[12px] font-semibold">{{ row.value }}</div>
                    <div class="mt-0.5 truncate text-[9px] uppercase tracking-wider opacity-70">
                      {{ row.label }}
                    </div>
                  </div>
                </div>
              }
            </div>

            @if (!preview.fits_context) {
              <div class="space-y-1 rounded border border-pink bg-pink/5 p-2 text-[11px]">
                <div class="flex items-center gap-1.5 font-semibold text-pink">
                  <mat-icon class="!h-4 !w-4 !text-[16px]">error_outline</mat-icon>
                  This prompt will not fit the model's context
                </div>
                @for (line of preview.budget_advice; track line) {
                  <p class="text-navy">{{ line }}</p>
                }
              </div>
            }
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

  /** Show the three blocks joined, or only the one being edited. */
  protected readonly fullPrompt = signal(false);
  protected readonly copied = signal(false);
  private readonly dialog = inject(MatDialog);

  protected selectSystem(id: string): void {
    this.store.selectedSystemPromptId.set(id);
    const version = this.store.systemPrompts().find((p) => p.id === id);
    if (version) this.store.systemPromptDraft.set(version.content);
  }

  protected selectTemplate(id: string): void {
    this.store.selectedTemplateId.set(id);
    const version = this.store.dynamicTemplates().find((p) => p.id === id);
    if (version) this.store.dynamicTemplateDraft.set(version.content);
  }

  protected async saveTemplate(): Promise<void> {
    const result = await this.ask({
      title: 'Save a new dynamic template version',
      hint: 'This controls how the EMG window is rendered — the only block that '
          + 'changes between runs. Alternative renderings are a legitimate '
          + 'experimental variable.',
      name: 'Custom dynamic template',
      version: this.nextVersion(this.store.dynamicTemplates().length),
      summary: [
        { label: 'Characters', value: String(this.store.dynamicTemplateDraft().length) },
        { label: 'Becomes active', value: 'yes' },
      ],
    });
    if (result) {
      await this.store.saveTemplateVersion(result.name, result.version ?? '1.0.0');
    }
  }

  /** Token accounting shown beside the preview. */
  /**
   * The token budget as four cards, one per block plus the total.
   *
   * Colour carries the meaning: navy for the two frozen blocks (fixed cost,
   * paid on every run), pink for the block that varies, and the total in amber
   * or pink depending on whether it fits. On a real recording the dynamic block
   * is an order of magnitude larger than the other two, and seeing that at a
   * glance is more useful than reading four numbers and comparing them.
   */
  protected tokenRows(preview: {
    token_breakdown: Record<string, number>;
    estimated_prompt_tokens: number;
    context_window: number | null;
    fits_context: boolean;
  }): { label: string; value: string; icon: string; tone: string; hint: string }[] {
    const b = preview.token_breakdown ?? {};
    const total = preview.estimated_prompt_tokens;
    const share = (n: number) => (total ? ` · ${Math.round((n / total) * 100)}% of the prompt` : '');

    return [
      {
        label: 'System',
        value: String(b['system_prompt'] ?? 0),
        icon: 'psychology',
        tone: 'bg-navy/5 text-navy',
        hint: 'Block 1 — behaviour and output discipline. Identical on every run.'
          + share(b['system_prompt'] ?? 0),
      },
      {
        label: 'Context',
        value: String(b['technical_context'] ?? 0),
        icon: 'precision_manufacturing',
        tone: 'bg-navy/10 text-navy',
        hint: 'Block 2 — the hand: commands, ranges, protocol, safety. Identical on every run.'
          + share(b['technical_context'] ?? 0),
      },
      {
        label: 'Dynamic',
        value: String(b['dynamic_prompt'] ?? 0),
        icon: 'monitor_heart',
        tone: 'bg-pink/10 text-pink',
        hint: 'Block 3 — the EMG for this run. The only block that changes, and usually the largest.'
          + share(b['dynamic_prompt'] ?? 0),
      },
      {
        label: preview.context_window ? 'Of context' : 'Total',
        value: preview.context_window ? `${total} / ${preview.context_window}` : String(total),
        icon: preview.fits_context ? 'check_circle' : 'error_outline',
        tone: preview.fits_context ? 'bg-amber/20 text-navy' : 'bg-pink text-white',
        hint: preview.context_window
          ? 'The context the model was loaded with — not what its architecture supports.'
          : 'Select a model to compare this against its context window.',
      },
    ];
  }

  /** Copy whichever view is on screen. */
  protected async copy(text: string): Promise<void> {
    await navigator.clipboard.writeText(text);
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1200);
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
    const result = await this.ask({
      title: 'Save a new system prompt version',
      hint: 'The behaviour contract. Keep it free of numeric limits so it can be '
          + 'versioned independently of the hardware description.',
      name: 'Custom system prompt',
      version: this.nextVersion(this.store.systemPrompts().length),
      summary: [
        { label: 'Characters', value: String(this.store.systemPromptDraft().length) },
        { label: 'Becomes active', value: 'yes' },
      ],
    });
    if (result) {
      await this.store.saveSystemPromptVersion(result.name, result.version ?? '1.0.0');
    }
  }

  protected async saveContext(): Promise<void> {
    const result = await this.ask({
      title: 'Save a new technical context version',
      hint: 'Editing this changes what the model is told about the hardware. '
          + 'Regenerate restores the canonical text derived from the code.',
      name: 'Custom technical context',
      version: this.nextVersion(this.store.technicalContexts().length),
      summary: [
        { label: 'Characters', value: String(this.store.technicalContextDraft().length) },
        { label: 'Limit profile', value: this.store.limitProfile() },
        { label: 'Becomes active', value: 'yes' },
      ],
    });
    if (result) {
      await this.store.saveContextVersion(result.name, result.version ?? '1.0.0');
    }
  }

  private ask(data: SaveDialogData) {
    return firstValueFrom(
      this.dialog.open(SaveDialog, { width: '440px', autoFocus: 'input', data }).afterClosed(),
    );
  }

  private nextVersion(count: number): string {
    return `1.${count + 1}.0`;
  }
}

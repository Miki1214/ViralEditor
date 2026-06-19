import { HOOK_FONT_OPTIONS } from "../constants/fonts";
import type { FormState } from "./JobForm";

interface HookOverlayPanelProps {
  form: FormState;
  onPatch: (partial: Partial<FormState>) => void;
}

export function HookOverlayPanel({ form, onPatch }: HookOverlayPanelProps) {
  return (
    <div className="panel space-y-4 p-5">
      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Hook & overlay
        </h2>
        <p className="mt-1 text-xs text-monitor-muted">
          Title text baked into the hook slot and composited preview.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block sm:col-span-2">
          <span className="field-label">Hook text</span>
          <input
            className="field-input mt-1"
            value={form.hookText}
            onChange={(e) => onPatch({ hookText: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="field-label">Emphasis words</span>
          <input
            className="field-input mt-1"
            value={form.emphasisWords}
            onChange={(e) => onPatch({ emphasisWords: e.target.value })}
            placeholder="30, days"
          />
        </label>
        <label className="block">
          <span className="field-label">Font</span>
          <select
            className="field-select mt-1"
            value={form.fontFamily}
            onChange={(e) => onPatch({ fontFamily: e.target.value })}
          >
            {HOOK_FONT_OPTIONS.map((font) => (
              <option key={font.value} value={font.value}>
                {font.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="field-label">Fill color</span>
          <input
            type="color"
            className="field-color"
            value={form.fillColor}
            onChange={(e) => onPatch({ fillColor: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="field-label">Emphasis color</span>
          <input
            type="color"
            className="field-color"
            value={form.emphasisColor}
            onChange={(e) => onPatch({ emphasisColor: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="field-label">Safe padding %</span>
          <input
            type="number"
            min={0}
            max={50}
            className="field-input mt-1"
            value={form.safePaddingPct}
            onChange={(e) =>
              onPatch({ safePaddingPct: Number(e.target.value) || 10 })
            }
          />
        </label>
      </div>
    </div>
  );
}

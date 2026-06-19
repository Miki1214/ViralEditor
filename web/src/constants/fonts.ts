/** Hook overlay fonts supported by the render pipeline. */

export interface HookFontOption {
  value: string;
  label: string;
}

export const HOOK_FONT_OPTIONS: HookFontOption[] = [
  { value: "Montserrat Black", label: "Montserrat Black" },
  { value: "Impact", label: "Impact" },
  { value: "Arial Black", label: "Arial Black" },
  { value: "Bebas Neue", label: "Bebas Neue" },
  { value: "Anton", label: "Anton" },
  { value: "Oswald", label: "Oswald" },
  { value: "Barlow Condensed Black", label: "Barlow Condensed Black" },
  { value: "Helvetica Neue", label: "Helvetica Neue Bold" },
];

export const DEFAULT_HOOK_FONT = HOOK_FONT_OPTIONS[0].value;

export function isHookFont(value: string): boolean {
  return HOOK_FONT_OPTIONS.some((option) => option.value === value);
}

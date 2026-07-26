/** One-click caption style presets (title + body). */

import type { CaptionStylePayload } from "../types";

export interface CaptionStylePreset {
  id: string;
  label: string;
  hook: Partial<CaptionStylePayload>;
  body: Partial<CaptionStylePayload>;
}

export const CAPTION_STYLE_PRESETS: CaptionStylePreset[] = [
  {
    id: "bold-impact",
    label: "Bold Impact",
    hook: {
      font_family: "Impact",
      fill_color: "#FFFFFF",
      emphasis_color: "#FFD700",
      outline_enabled: true,
      box_enabled: true,
      position: "top",
      size_scale: 1.2,
    },
    body: {
      font_family: "Impact",
      fill_color: "#FFFFFF",
      emphasis_color: "#FFD700",
      outline_enabled: true,
      box_enabled: false,
      position: "bottom",
      size_scale: 1.1,
    },
  },
  {
    id: "clean-subtitle",
    label: "Clean Subtitle",
    hook: {
      font_family: "Montserrat Black",
      fill_color: "#FFFFFF",
      emphasis_color: "#FFFFFF",
      outline_enabled: false,
      box_enabled: true,
      box_color: "rgba(0,0,0,0.75)",
      position: "top",
      size_scale: 1.0,
    },
    body: {
      font_family: "Montserrat Black",
      fill_color: "#FFFFFF",
      emphasis_color: "#FFFFFF",
      outline_enabled: false,
      box_enabled: true,
      box_color: "rgba(0,0,0,0.75)",
      position: "bottom",
      size_scale: 0.95,
    },
  },
  {
    id: "neon-pop",
    label: "Neon Pop",
    hook: {
      font_family: "Bebas Neue",
      fill_color: "#00FFCC",
      emphasis_color: "#FF00AA",
      outline_color: "#000000",
      outline_enabled: true,
      box_enabled: false,
      position: "top",
      size_scale: 1.15,
    },
    body: {
      font_family: "Bebas Neue",
      fill_color: "#00FFCC",
      emphasis_color: "#FF00AA",
      outline_color: "#000000",
      outline_enabled: true,
      box_enabled: false,
      position: "center",
      size_scale: 1.05,
    },
  },
];

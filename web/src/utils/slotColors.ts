/** Per-slot colors tuned for deuteranopia/protanopia — wide hue + lightness spread. */

export interface SlotColor {
  stroke: string;
  fill: string;
  fillActive: string;
  border: string;
  bg: string;
}

export const SLOT_COLOR_PALETTE: SlotColor[] = [
  {
    stroke: "#F0C929",
    fill: "rgba(240,201,41,0.10)",
    fillActive: "rgba(240,201,41,0.30)",
    border: "rgba(240,201,41,0.65)",
    bg: "rgba(240,201,41,0.12)",
  },
  {
    stroke: "#5B9FE3",
    fill: "rgba(91,159,227,0.10)",
    fillActive: "rgba(91,159,227,0.30)",
    border: "rgba(91,159,227,0.65)",
    bg: "rgba(91,159,227,0.12)",
  },
  {
    stroke: "#E87878",
    fill: "rgba(232,120,120,0.10)",
    fillActive: "rgba(232,120,120,0.30)",
    border: "rgba(232,120,120,0.65)",
    bg: "rgba(232,120,120,0.12)",
  },
  {
    stroke: "#C77DFF",
    fill: "rgba(199,125,255,0.10)",
    fillActive: "rgba(199,125,255,0.30)",
    border: "rgba(199,125,255,0.65)",
    bg: "rgba(199,125,255,0.12)",
  },
  {
    stroke: "#FF9933",
    fill: "rgba(255,153,51,0.10)",
    fillActive: "rgba(255,153,51,0.30)",
    border: "rgba(255,153,51,0.65)",
    bg: "rgba(255,153,51,0.12)",
  },
  {
    stroke: "#67E8F9",
    fill: "rgba(103,232,249,0.10)",
    fillActive: "rgba(103,232,249,0.30)",
    border: "rgba(103,232,249,0.65)",
    bg: "rgba(103,232,249,0.12)",
  },
  {
    stroke: "#F472B6",
    fill: "rgba(244,114,182,0.10)",
    fillActive: "rgba(244,114,182,0.30)",
    border: "rgba(244,114,182,0.65)",
    bg: "rgba(244,114,182,0.12)",
  },
  {
    stroke: "#9D94FF",
    fill: "rgba(157,148,255,0.10)",
    fillActive: "rgba(157,148,255,0.30)",
    border: "rgba(157,148,255,0.65)",
    bg: "rgba(157,148,255,0.12)",
  },
];

export function slotColorForIndex(index: number): SlotColor {
  const len = SLOT_COLOR_PALETTE.length;
  return SLOT_COLOR_PALETTE[((index % len) + len) % len];
}

/** Portrait output aspect (width / height). */
export const PORTRAIT_ASPECT = 9 / 16;

export interface PixelRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface NormalizedRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function effectiveVideoSize(
  videoWidth: number,
  videoHeight: number,
  rotationDeg: number,
): { width: number; height: number } {
  const swap = rotationDeg % 180 === 90;
  return swap
    ? { width: videoHeight, height: videoWidth }
    : { width: videoWidth, height: videoHeight };
}

/** Object-contain display rect inside a container (post-rotation logical frame). */
export function objectContainRect(
  containerW: number,
  containerH: number,
  frameW: number,
  frameH: number,
): PixelRect {
  if (frameW <= 0 || frameH <= 0 || containerW <= 0 || containerH <= 0) {
    return { x: 0, y: 0, w: containerW, h: containerH };
  }
  const scale = Math.min(containerW / frameW, containerH / frameH);
  const w = frameW * scale;
  const h = frameH * scale;
  return {
    x: (containerW - w) / 2,
    y: (containerH - h) / 2,
    w,
    h,
  };
}

/** Largest portrait-aspect rect centered inside bounds. */
export function defaultPortraitCrop(bounds: PixelRect): PixelRect {
  let w = bounds.w;
  let h = w / PORTRAIT_ASPECT;
  if (h > bounds.h) {
    h = bounds.h;
    w = h * PORTRAIT_ASPECT;
  }
  return {
    x: bounds.x + (bounds.w - w) / 2,
    y: bounds.y + (bounds.h - h) / 2,
    w,
    h,
  };
}

export function normalizedToPixelRect(norm: NormalizedRect, bounds: PixelRect): PixelRect {
  return {
    x: bounds.x + norm.x * bounds.w,
    y: bounds.y + norm.y * bounds.h,
    w: norm.w * bounds.w,
    h: norm.h * bounds.h,
  };
}

export function pixelRectToNormalized(box: PixelRect, bounds: PixelRect): NormalizedRect {
  const x = clamp01((box.x - bounds.x) / bounds.w);
  const y = clamp01((box.y - bounds.y) / bounds.h);
  const right = clamp01((box.x + box.w - bounds.x) / bounds.w);
  const bottom = clamp01((box.y + box.h - bounds.y) / bounds.h);
  return {
    x,
    y,
    w: Math.max(0.02, right - x),
    h: Math.max(0.02, bottom - y),
  };
}

export function clampCropBox(box: PixelRect, bounds: PixelRect, minW = 48): PixelRect {
  const aspect = PORTRAIT_ASPECT;
  let w = Math.max(minW, Math.min(box.w, bounds.w));
  let h = w / aspect;
  if (h > bounds.h) {
    h = bounds.h;
    w = h * aspect;
  }
  w = Math.max(minW, w);
  h = w / aspect;

  let x = box.x;
  let y = box.y;
  x = Math.max(bounds.x, Math.min(x, bounds.x + bounds.w - w));
  y = Math.max(bounds.y, Math.min(y, bounds.y + bounds.h - h));
  return { x, y, w, h };
}

/** Clamp size while keeping the top-left corner fixed (SE resize). */
export function clampCropBoxSe(
  anchorX: number,
  anchorY: number,
  w: number,
  bounds: PixelRect,
  minW = 48,
): PixelRect {
  const aspect = PORTRAIT_ASPECT;
  const maxW = bounds.x + bounds.w - anchorX;
  const maxH = bounds.y + bounds.h - anchorY;

  let width = Math.max(minW, Math.min(w, maxW));
  let height = width / aspect;
  if (height > maxH) {
    height = maxH;
    width = height * aspect;
  }
  width = Math.max(minW, width);
  height = width / aspect;
  return { x: anchorX, y: anchorY, w: width, h: height };
}

/** Clamp size while keeping the bottom-right corner fixed (NW resize). */
export function clampCropBoxNw(
  fixedRight: number,
  fixedBottom: number,
  w: number,
  bounds: PixelRect,
  minW = 48,
): PixelRect {
  const aspect = PORTRAIT_ASPECT;
  const maxW = fixedRight - bounds.x;
  const maxH = fixedBottom - bounds.y;

  let width = Math.max(minW, Math.min(w, maxW));
  let height = width / aspect;
  if (height > maxH) {
    height = maxH;
    width = height * aspect;
  }
  width = Math.max(minW, width);
  height = width / aspect;

  let x = fixedRight - width;
  let y = fixedBottom - height;
  return { x, y, w: width, h: height };
}

export function resizeCropByDelta(
  startBox: PixelRect,
  dx: number,
  dy: number,
  bounds: PixelRect,
  corner: "se" | "nw",
  minW = 48,
): PixelRect {
  const aspect = PORTRAIT_ASPECT;
  const fixedRight = startBox.x + startBox.w;
  const fixedBottom = startBox.y + startBox.h;

  if (corner === "se") {
    const wFromX = startBox.w + dx;
    const wFromY = (startBox.h + dy) * aspect;
    const w = Math.max(wFromX, wFromY, minW);
    return clampCropBoxSe(startBox.x, startBox.y, w, bounds, minW);
  }

  const wFromX = startBox.w - dx;
  const wFromY = (startBox.h - dy) * aspect;
  const w = Math.max(wFromX, wFromY, minW);
  return clampCropBoxNw(fixedRight, fixedBottom, w, bounds, minW);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

/** CSS for previewing a normalized spatial crop in a 9:16 viewport. */
export function spatialCropPreviewStyle(crop: NormalizedRect): {
  width: string;
  height: string;
  left: string;
  top: string;
} {
  return {
    width: `${(100 / crop.w).toFixed(4)}%`,
    height: `${(100 / crop.h).toFixed(4)}%`,
    left: `${((-crop.x / crop.w) * 100).toFixed(4)}%`,
    top: `${((-crop.y / crop.h) * 100).toFixed(4)}%`,
  };
}

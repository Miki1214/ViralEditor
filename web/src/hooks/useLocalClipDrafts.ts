import { useCallback, useEffect, type Dispatch, type SetStateAction } from "react";
import type { LocalClipDraft } from "../components/ClipReelPanel";
import type { FormState } from "../components/JobForm";

export type LocalClipsUpdater =
  | LocalClipDraft[]
  | ((prev: LocalClipDraft[]) => LocalClipDraft[]);

export function clipFilesChanged(
  previous: LocalClipDraft[],
  next: LocalClipDraft[],
): boolean {
  if (previous.length !== next.length) return true;
  return next.some((clip, index) => clip.file !== previous[index]?.file);
}

export function useUpdateLocalClips(
  setForm: Dispatch<SetStateAction<FormState>>,
  onFilesChanged: () => void,
) {
  return useCallback(
    (update: LocalClipsUpdater) => {
      setForm((prev) => {
        const localClips = typeof update === "function" ? update(prev.localClips) : update;
        if (clipFilesChanged(prev.localClips, localClips)) {
          queueMicrotask(onFilesChanged);
        }
        return { ...prev, localClips };
      });
    },
    [setForm, onFilesChanged],
  );
}

export function useProbeClipDurations(
  clips: LocalClipDraft[],
  updateClips: (update: LocalClipsUpdater) => void,
) {
  const pendingSignature = clips
    .filter((clip) => clip.durationS == null)
    .map((clip) => `${clip.id}:${clip.previewUrl}`)
    .join("|");

  useEffect(() => {
    const pending = clips.filter((clip) => clip.durationS == null);
    if (pending.length === 0) return;

    const cleanups: Array<() => void> = [];

    for (const clip of pending) {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.src = clip.previewUrl;

      const applyDuration = () => {
        const duration = Number.isFinite(video.duration) ? video.duration : null;
        updateClips((current) =>
          current.map((item) =>
            item.id === clip.id
              ? {
                  ...item,
                  durationS: duration,
                  cropEndS: duration,
                }
              : item,
          ),
        );
      };

      video.addEventListener("loadedmetadata", applyDuration);
      video.addEventListener("error", applyDuration);
      cleanups.push(() => {
        video.removeEventListener("loadedmetadata", applyDuration);
        video.removeEventListener("error", applyDuration);
        video.removeAttribute("src");
        video.load();
      });
    }

    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }, [pendingSignature, clips, updateClips]);
}
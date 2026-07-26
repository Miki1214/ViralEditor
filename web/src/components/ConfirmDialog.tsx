import { useEffect } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmDisabled = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      id="confirm-dialog-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <button
        id="confirm-dialog-close-btn"
        type="button"
        className="absolute inset-0 bg-monitor-bg/70 backdrop-blur-sm"
        aria-label="Close dialog"
        onClick={onCancel}
      />
      <div
        id="confirm-dialog-container"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        className="panel relative z-10 w-full max-w-md space-y-4 p-5 shadow-xl"
      >
        <div>
          <h2
            id="confirm-dialog-title"
            className="text-sm font-semibold tracking-tight"
          >
            {title}
          </h2>
          <p id="confirm-dialog-message" className="mt-2 text-sm text-monitor-muted">
            {message}
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <button id="confirm-dialog-cancel-btn" type="button" className="btn-ghost text-xs" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            id="confirm-dialog-confirm-btn"
            type="button"
            className="btn-primary text-xs"
            disabled={confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

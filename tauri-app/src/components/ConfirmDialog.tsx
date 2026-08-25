import React, {useEffect, type ReactNode} from 'react';
import {AlertTriangle, Loader2, X} from 'lucide-react';
import {Button} from './ui';

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: ReactNode;
  entityName?: string | undefined;
  confirmLabel?: string | undefined;
  confirmLoadingLabel?: string | undefined;
  cancelLabel?: string | undefined;
  isLoading?: boolean | undefined;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  entityName,
  confirmLabel = 'Confirm',
  confirmLoadingLabel = 'Processing...',
  cancelLabel = 'Cancel',
  isLoading = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, isLoading, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4 animate-in fade-in duration-150"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !isLoading) {
          onClose();
        }
      }}
    >
      <div className="relative w-full max-w-md rounded-xl border border-cursor-hairline bg-cursor-surface-card p-5 shadow-lg animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-start gap-3.5">
          <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-cursor-semantic-error/10 text-cursor-semantic-error">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <h3 id="confirm-dialog-title" className="m-0 text-base font-semibold leading-snug text-cursor-ink">
                {title}
              </h3>
              {!isLoading && (
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md p-1 text-cursor-muted transition-colors hover:bg-cursor-canvas-soft hover:text-cursor-ink cursor-pointer"
                  title="Close"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Entity Badge / Name */}
            {entityName && (
              <div className="mt-2 inline-flex max-w-full items-center rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-2 py-0.5 font-mono text-xs font-medium text-cursor-ink truncate">
                {entityName}
              </div>
            )}

            {/* Description */}
            <div className="mt-2.5 text-xs leading-relaxed text-cursor-body">
              {description}
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="mt-6 flex items-center justify-end gap-2.5 border-t border-cursor-hairline-soft pt-4">
          <Button
            variant="ghost"
            disabled={isLoading}
            onClick={onClose}
            className="px-3.5 text-xs"
          >
            {cancelLabel}
          </Button>
          <Button
            variant="danger"
            disabled={isLoading}
            onClick={() => void onConfirm()}
            icon={isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : undefined}
            className="px-3.5 text-xs font-medium"
          >
            {isLoading ? confirmLoadingLabel : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

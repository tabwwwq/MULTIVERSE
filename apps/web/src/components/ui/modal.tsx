"use client";

import { X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { Button, type ButtonProps } from "@/components/ui/button";

/*
 * Native modal <dialog> opened with showModal(), as the dialog guidance requires:
 * the browser provides the inert page, focus containment, Esc, the backdrop and
 * focus return to the trigger. No role="dialog", aria-modal or manual focus trap.
 */

interface ModalProps {
  title: string;
  description?: ReactNode;
  triggerLabel: string;
  triggerVariant?: ButtonProps["variant"];
  /** The safe action. It receives initial focus (autofocus). */
  cancelLabel: string;
  confirmLabel: string;
  confirmVariant?: ButtonProps["variant"];
  onClose?: (result: "confirm" | "cancel" | "dismissed") => void;
}

export function Modal({
  title,
  description,
  triggerLabel,
  triggerVariant = "secondary",
  cancelLabel,
  confirmLabel,
  confirmVariant = "danger",
  onClose,
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    // React's autoFocus prop focuses on mount; the dialog needs the real attribute instead,
    // so focus moves to the safe action only when the dialog opens.
    cancelRef.current?.setAttribute("autofocus", "");
    const dialog = dialogRef.current;
    if (!dialog) return;
    const handleClose = () => {
      const value = dialog.returnValue;
      dialog.returnValue = "";
      onClose?.(value === "confirm" ? "confirm" : value === "cancel" ? "cancel" : "dismissed");
    };
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [onClose]);

  return (
    <>
      <Button variant={triggerVariant} onClick={() => dialogRef.current?.showModal()}>
        {triggerLabel}
      </Button>
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        // Light dismiss where supported; Esc and the back gesture work everywhere.
        {...{ closedby: "any" }}
        className="modal"
      >
        <form method="dialog" className="flex flex-col gap-5">
          <div className="flex items-start justify-between gap-4">
            <h2 id={titleId} className="font-display text-h4 text-ink">
              {title}
            </h2>
            <button
              value="dismissed"
              aria-label="Close"
              className="-m-2 rounded-control p-2 text-ink-muted hover:bg-inset hover:text-ink"
            >
              <X aria-hidden="true" className="size-5" />
            </button>
          </div>
          {description ? (
            <div id={descriptionId} className="text-body text-ink-muted">
              {description}
            </div>
          ) : null}
          <div className="flex flex-wrap justify-end gap-3">
            <Button ref={cancelRef} type="submit" value="cancel" variant="secondary">
              {cancelLabel}
            </Button>
            <Button type="submit" value="confirm" variant={confirmVariant}>
              {confirmLabel}
            </Button>
          </div>
        </form>
      </dialog>
    </>
  );
}

import { useEffect, useRef } from "react";
import s from "./Modal.module.css";

export function Modal({
  title,
  onClose,
  children,
  actions,
}: {
  title: string;
  onClose?: () => void;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("button, [href]")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose?.();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div className={s.backdrop} onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div ref={ref} className={s.dialog} role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h2 id="modal-title" className={s.title}>
          {title}
        </h2>
        <div className={s.body}>{children}</div>
        {actions && <div className={s.actions}>{actions}</div>}
      </div>
    </div>
  );
}

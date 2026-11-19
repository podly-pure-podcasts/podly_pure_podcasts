import { type ReactNode, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface ModalShellProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  containerClassName?: string;
  panelClassName?: string;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
}

const EXIT_TRANSITION_MS = 380;

export default function ModalShell({
  isOpen,
  onClose,
  children,
  containerClassName = 'items-center p-4',
  panelClassName = '',
  closeOnBackdrop = true,
  closeOnEscape = true,
}: ModalShellProps) {
  const [isMounted, setIsMounted] = useState(isOpen);
  const [isVisible, setIsVisible] = useState(isOpen);

  useEffect(() => {
    if (isOpen) {
      setIsMounted(true);
      setIsVisible(false);
      let firstFrame = 0;
      let secondFrame = 0;
      firstFrame = window.requestAnimationFrame(() => {
        secondFrame = window.requestAnimationFrame(() => {
          setIsVisible(true);
        });
      });
      return () => {
        window.cancelAnimationFrame(firstFrame);
        window.cancelAnimationFrame(secondFrame);
      };
    }

    setIsVisible(false);
    const timeout = window.setTimeout(() => {
      setIsMounted(false);
    }, EXIT_TRANSITION_MS);
    return () => {
      window.clearTimeout(timeout);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isMounted || typeof document === 'undefined') {
      return;
    }

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [isMounted]);

  useEffect(() => {
    if (!isMounted || !closeOnEscape) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [closeOnEscape, isMounted, onClose]);

  if (!isMounted) {
    return null;
  }

  const state = isVisible ? 'open' : 'closed';
  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <div
      className={`fixed inset-0 z-50 flex justify-center ${containerClassName}`}
      data-state={state}
    >
      <div
        aria-hidden="true"
        className="podly-modal-backdrop absolute inset-0"
        data-state={state}
        onClick={closeOnBackdrop ? onClose : undefined}
      />
      <div
        className={`podly-modal-panel relative ${panelClassName}`.trim()}
        data-state={state}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </div>,
    document.body
  );
}

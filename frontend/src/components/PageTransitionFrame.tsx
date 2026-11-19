import { type ReactNode, useEffect, useState } from 'react';

interface PageTransitionFrameProps {
  children: ReactNode;
  className?: string;
  transitionKey: string;
  animateOnMount?: boolean;
}

export default function PageTransitionFrame({
  children,
  className = '',
  transitionKey,
  animateOnMount = true,
}: PageTransitionFrameProps) {
  const [isVisible, setIsVisible] = useState(!animateOnMount);

  useEffect(() => {
    if (!animateOnMount) {
      setIsVisible(true);
      return;
    }

    let firstFrame = 0;
    let secondFrame = 0;

    setIsVisible(false);
    firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        setIsVisible(true);
      });
    });

    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.cancelAnimationFrame(secondFrame);
    };
  }, [animateOnMount, transitionKey]);

  return (
    <div
      className={`podly-page-transition ${className}`.trim()}
      data-state={isVisible ? 'open' : 'closed'}
    >
      {children}
    </div>
  );
}

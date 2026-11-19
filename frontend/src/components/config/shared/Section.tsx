import type { ReactNode } from 'react';
import { ChevronDownIcon } from '../../icons';

interface SectionProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Starts collapsed; for settings most people never change. */
  collapsible?: boolean;
  /** Keep the card and full-width body on desktop, for tables and dashboards. */
  stacked?: boolean;
}

const card = 'rounded-lg border border-gray-200 bg-surface p-4 shadow-sm sm:p-5';
// From `lg` a settings section drops its card and becomes a hairline-separated row:
// heading in a 15rem column, fields beside it.
const row =
  'lg:rounded-none lg:border-0 lg:border-t lg:bg-transparent lg:px-0 lg:pb-0 lg:pt-6 lg:shadow-none lg:first:border-t-0 lg:first:pt-0';
const split = 'lg:grid lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10';

export default function Section({
  title,
  description,
  children,
  className = '',
  collapsible = false,
  stacked = false,
}: SectionProps) {
  const frame = stacked ? card : `${card} ${row}`;
  const heading = (
    <div className="min-w-0">
      <h3 className="text-base font-semibold text-gray-900">{title}</h3>
      {description ? <p className="mt-0.5 text-sm text-gray-600">{description}</p> : null}
    </div>
  );
  // `self-start` keeps the body from stretching to the row height; a stretched
  // grid item gives Field's `h-full` a definite height to fill.
  const body = <div className="min-w-0 space-y-5 self-start">{children}</div>;

  if (collapsible) {
    return (
      <details className={`group ${frame} ${className}`}>
        <summary className="flex cursor-pointer list-none items-start justify-between gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 [&::-webkit-details-marker]:hidden">
          {heading}
          <ChevronDownIcon className="mt-0.5 h-5 w-5 shrink-0 text-gray-500 transition-transform duration-200 group-open:rotate-180" />
        </summary>
        <div className={`mt-5 ${stacked ? '' : 'lg:ml-[17.5rem]'}`}>{body}</div>
      </details>
    );
  }

  return (
    <section className={`${frame} ${stacked ? '' : split} ${className}`}>
      <div className={stacked ? 'mb-5' : 'mb-5 lg:mb-0'}>{heading}</div>
      {body}
    </section>
  );
}

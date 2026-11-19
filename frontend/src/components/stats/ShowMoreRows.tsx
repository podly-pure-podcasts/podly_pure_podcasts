export const ROW_PAGE_SIZE = 200;

interface ShowMoreRowsProps {
  shown: number;
  total: number;
  onShowMore: () => void;
}

export default function ShowMoreRows({ shown, total, onShowMore }: ShowMoreRowsProps) {
  const visible = Math.min(shown, total);
  return (
    <div className="mt-3 flex items-center gap-3">
      {visible < total && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onShowMore}>
          Show {ROW_PAGE_SIZE} more
        </button>
      )}
      <span className="text-xs text-gray-600 tabular-nums">
        Showing {visible.toLocaleString()} of {total.toLocaleString()}
      </span>
    </div>
  );
}

interface TestButtonProps {
  onClick: () => void;
  label: string;
  className?: string;
}

export default function TestButton({ onClick, label, className = '' }: TestButtonProps) {
  return (
    <div className={className}>
      <button type="button" onClick={onClick} className="btn btn-secondary">
        {label}
      </button>
    </div>
  );
}

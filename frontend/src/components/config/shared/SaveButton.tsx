interface SaveButtonProps {
  onSave: () => void;
  isPending: boolean;
  className?: string;
}

export default function SaveButton({ onSave, isPending, className = '' }: SaveButtonProps) {
  return (
    <div className={`flex items-center justify-end ${className}`}>
      <button onClick={onSave} className="btn btn-primary" disabled={isPending}>
        {isPending ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  );
}

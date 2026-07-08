"use client";

type Props = {
  onRestore: () => void;
};

export function PanelRestoreTab({ onRestore }: Props) {
  return (
    <button
      type="button"
      aria-label="Open chains panel"
      className="panel-restore-tab fixed left-0 z-20 flex items-center justify-center"
      onClick={onRestore}
    >
      <ChevronRightIcon />
    </button>
  );
}

function ChevronRightIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M7.21 14.77a.75.75 0 0 1 .02-1.06L11.168 10 7.23 6.29a.75.75 0 1 1 1.04-1.08l4.5 4.25a.75.75 0 0 1 0 1.08l-4.5 4.25a.75.75 0 0 1-1.06-.02Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

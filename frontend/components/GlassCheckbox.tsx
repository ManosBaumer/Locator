"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
};

export function GlassCheckbox({
  checked,
  indeterminate = false,
  onChange,
  className = ""
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [popping, setPopping] = useState(false);

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);

  useEffect(() => {
    if (!popping) {
      return;
    }

    const timeout = window.setTimeout(() => setPopping(false), 220);
    return () => window.clearTimeout(timeout);
  }, [popping]);

  const stateClass = indeterminate ? "is-indeterminate" : checked ? "is-checked" : "";

  function handleChange(nextChecked: boolean) {
    setPopping(true);
    onChange(nextChecked);
  }

  return (
    <>
      <input
        ref={inputRef}
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        onChange={(event) => handleChange(event.target.checked)}
      />
      <span
        className={`glass-checkbox pointer-events-none ${stateClass} ${popping ? "is-popping" : ""} ${className}`}
        aria-hidden="true"
      >
        {indeterminate ? <MinusIcon /> : checked ? <CheckIcon /> : null}
      </span>
    </>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5" aria-hidden="true">
      <path
        d="M2.5 6.2 5.1 8.8 9.5 3.8"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MinusIcon() {
  return (
    <svg viewBox="0 0 12 12" fill="none" className="h-2.5 w-2.5" aria-hidden="true">
      <path
        d="M2.5 6h7"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

import { chainLogoPath } from "@/lib/chain-logos";

type Props = {
  slug: string;
  size?: "sm" | "md";
  className?: string;
};

const sizeClasses = {
  sm: "h-5 w-5 max-h-5 max-w-5",
  md: "h-6 w-6 max-h-6 max-w-6",
  lg: "h-8 w-8 max-h-8 max-w-8"
} as const;

export function ChainLogo({ slug, size = "sm", className = "" }: Props) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${sizeClasses[size]} ${className}`}
    >
      <img
        src={chainLogoPath(slug)}
        alt=""
        className="max-h-full max-w-full object-contain"
        loading="lazy"
      />
    </span>
  );
}

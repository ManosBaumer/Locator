import { SITE_NAME } from "@/lib/site";

/** Mobile header wordmark — first letter uses extra width on the Anybody variable axis. */
export function MobileBrandMark() {
  const [firstLetter, ...rest] = SITE_NAME;
  const tail = rest.join("");

  return (
    <p className="mitu-brand-mark">
      <span className="mitu-brand-m">{firstLetter}</span>
      {tail}
    </p>
  );
}

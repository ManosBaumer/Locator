import { ChainLogo } from "@/components/ChainLogo";
import { chainLabel } from "@/lib/chain-logos";
import type { LocationProperties } from "@/lib/types";

type Props = {
  location: LocationProperties;
};

export function LocationPopup({ location }: Props) {
  return (
    <div className="max-w-xs space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <ChainLogo slug={location.chain_slug} size="md" />
        <div className="min-w-0">
          <div className="font-semibold text-slate-900">{location.name ?? "Unnamed location"}</div>
          <div className="text-xs text-slate-500">{chainLabel(location.chain_slug)}</div>
        </div>
      </div>
      <div className="text-slate-600">{location.address ?? "No address available"}</div>
      <div className="text-xs text-slate-500">{location.city ?? "Unknown city"}</div>
    </div>
  );
}

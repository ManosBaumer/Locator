"use client";

import { ChainLogo } from "@/components/ChainLogo";
import type { Category, Chain } from "@/lib/types";

type Props = {
  categories: Category[];
  chains: Chain[];
  selectedCategories: string[];
  selectedChains: string[];
  onCategoriesChange: (slugs: string[]) => void;
  onChainsChange: (slugs: string[]) => void;
};

const checkboxClassName = "h-5 w-5 shrink-0 cursor-pointer accent-slate-900";

export function FilterPanel({
  categories,
  chains,
  selectedCategories,
  selectedChains,
  onCategoriesChange,
  onChainsChange
}: Props) {
  return (
    <section className="space-y-6 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div>
        <h2 className="text-base font-semibold text-slate-900">Categories</h2>
        <div className="mt-4 space-y-1">
          {categories.map((category) => (
            <label
              key={category.slug}
              className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-1 py-2.5 text-base text-slate-700"
            >
              <span className="min-w-0 truncate">{category.name}</span>
              <input
                type="checkbox"
                className={checkboxClassName}
                checked={selectedCategories.includes(category.slug)}
                onChange={(event) =>
                  onCategoriesChange(toggle(selectedCategories, category.slug, event.target.checked))
                }
              />
            </label>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-base font-semibold text-slate-900">Chains</h2>
        <div className="mt-4 space-y-1">
          {chains.map((chain) => (
            <label
              key={chain.slug}
              className="flex cursor-pointer items-center justify-between gap-3 rounded-lg px-1 py-2.5"
            >
              <span className="flex min-w-0 items-center gap-3">
                <ChainLogo slug={chain.slug} size="lg" />
                <span className="truncate text-base text-slate-700">{chain.name}</span>
              </span>
              <span className="flex shrink-0 items-center gap-3">
                <span className="tabular-nums text-sm text-slate-400">
                  {(chain.location_count ?? 0).toLocaleString()}
                </span>
                <input
                  type="checkbox"
                  className={checkboxClassName}
                  checked={selectedChains.includes(chain.slug)}
                  onChange={(event) =>
                    onChainsChange(toggle(selectedChains, chain.slug, event.target.checked))
                  }
                />
              </span>
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}

function toggle(values: string[], value: string, checked: boolean): string[] {
  if (checked) {
    return [...new Set([...values, value])];
  }
  return values.filter((item) => item !== value);
}

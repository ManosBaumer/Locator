"use client";

import { ChainLogo } from "@/components/ChainLogo";
import { GlassCheckbox } from "@/components/GlassCheckbox";
import { GlassScrollArea } from "@/components/GlassScrollArea";
import type { Category, Chain } from "@/lib/types";
import type { HTMLAttributes } from "react";
import { useEffect, useState } from "react";

type Props = {
  categories: Category[];
  chains: Chain[];
  selectedCategories: string[];
  selectedChains: string[];
  defaultExpandAll?: boolean;
  dragHandleProps?: HTMLAttributes<HTMLElement>;
  isDragging?: boolean;
  onMinimize?: () => void;
  onCategoriesChange: (slugs: string[]) => void;
  onChainsChange: (slugs: string[]) => void;
};

export function FilterPanel({
  categories,
  chains,
  selectedCategories,
  selectedChains,
  defaultExpandAll = false,
  dragHandleProps,
  isDragging = false,
  onMinimize,
  onCategoriesChange,
  onChainsChange
}: Props) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!defaultExpandAll || categories.length === 0) {
      return;
    }

    setExpandedCategories((current) => {
      if (current.size > 0) {
        return current;
      }
      return new Set(categories.map((category) => category.slug));
    });
  }, [categories, defaultExpandAll]);

  function toggleExpanded(categorySlug: string) {
    setExpandedCategories((current) => {
      const next = new Set(current);
      if (next.has(categorySlug)) {
        next.delete(categorySlug);
      } else {
        next.add(categorySlug);
      }
      return next;
    });
  }

  function chainsForCategory(categorySlug: string): Chain[] {
    return chains.filter((chain) => chain.category_slug === categorySlug);
  }

  function handleCategoryToggle(categorySlug: string, checked: boolean) {
    const categoryChains = chainsForCategory(categorySlug);
    const categoryChainSlugs = categoryChains.map((chain) => chain.slug);

    if (checked) {
      onChainsChange([...new Set([...selectedChains, ...categoryChainSlugs])]);
      onCategoriesChange([...new Set([...selectedCategories, categorySlug])]);
      return;
    }

    onChainsChange(selectedChains.filter((slug) => !categoryChainSlugs.includes(slug)));
    onCategoriesChange(selectedCategories.filter((slug) => slug !== categorySlug));
  }

  return (
    <section className="glass-panel flex max-h-[calc(100dvh-2rem)] min-h-0 flex-col overflow-hidden rounded-2xl [text-shadow:0_1px_1px_rgba(255,255,255,0.6)]">
      <header className="glass-panel-header flex shrink-0 items-start gap-2 px-3 py-4">
        <div
          {...dragHandleProps}
          className={`min-w-0 flex-1 touch-none select-none px-2 ${dragHandleProps?.className ?? ""} ${isDragging ? "cursor-grabbing" : dragHandleProps ? "cursor-grab" : ""}`}
        >
          <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-slate-500">Locater</p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">Chains</h2>
        </div>

        {onMinimize ? (
          <button
            type="button"
            aria-label="Minimize panel"
            className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white/35 hover:text-slate-800"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={onMinimize}
          >
            <MinimizeIcon />
          </button>
        ) : null}
      </header>

      <GlassScrollArea>
        <div className="divide-y divide-slate-900/5">
          {categories.map((category) => {
            const categoryChains = chainsForCategory(category.slug);
            if (categoryChains.length === 0) {
              return null;
            }

            const expanded = expandedCategories.has(category.slug);
            const selectedInCategory = categoryChains.filter((chain) =>
              selectedChains.includes(chain.slug)
            );
            const allSelected =
              categoryChains.length > 0 && selectedInCategory.length === categoryChains.length;
            const someSelected =
              selectedInCategory.length > 0 && selectedInCategory.length < categoryChains.length;

            return (
              <div key={category.slug} className="py-1">
                <div className="flex items-center gap-1.5 rounded-xl px-2 py-2 transition-colors hover:bg-white/25">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-label={`${expanded ? "Collapse" : "Expand"} ${category.name}`}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white/30 hover:text-slate-800"
                    onClick={() => toggleExpanded(category.slug)}
                  >
                    <ChevronIcon expanded={expanded} />
                  </button>

                  <label className="inline-flex shrink-0 cursor-pointer">
                    <GlassCheckbox
                      checked={allSelected}
                      indeterminate={someSelected}
                      onChange={(checked) => handleCategoryToggle(category.slug, checked)}
                    />
                  </label>

                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left text-sm font-medium text-slate-800"
                    onClick={() => toggleExpanded(category.slug)}
                  >
                    {category.name}
                  </button>

                  <span className="shrink-0 rounded-full bg-white/30 px-2 py-0.5 text-xs tabular-nums text-slate-600">
                    {selectedInCategory.length}/{categoryChains.length}
                  </span>
                </div>

                {expanded ? (
                  <div className="mb-2 ml-9 space-y-0.5 border-l border-slate-900/10 pl-3">
                    {categoryChains.map((chain) => (
                      <label
                        key={chain.slug}
                        className="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-white/25"
                      >
                        <span className="flex min-w-0 items-center gap-2.5">
                          <ChainLogo slug={chain.slug} size="md" />
                          <span className="truncate text-sm text-slate-800">{chain.name}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2.5">
                          <span className="tabular-nums text-xs text-slate-500">
                            {(chain.location_count ?? 0).toLocaleString()}
                          </span>
                          <GlassCheckbox
                            checked={selectedChains.includes(chain.slug)}
                            onChange={(checked) =>
                              onChainsChange(toggle(selectedChains, chain.slug, checked))
                            }
                          />
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </GlassScrollArea>
    </section>
  );
}

function MinimizeIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M12.79 5.23a.75.75 0 0 1-.02 1.06L9.832 10l3.938 3.71a.75.75 0 1 1-1.04 1.08l-4.5-4.25a.75.75 0 0 1 0-1.08l4.5-4.25a.75.75 0 0 1 1.06.02Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-4 w-4 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M7.21 14.77a.75.75 0 0 1 .02-1.06L11.168 10 7.23 6.29a.75.75 0 1 1 1.04-1.08l4.5 4.25a.75.75 0 0 1 0 1.08l-4.5 4.25a.75.75 0 0 1-1.06-.02Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function toggle(values: string[], value: string, checked: boolean): string[] {
  if (checked) {
    return [...new Set([...values, value])];
  }
  return values.filter((item) => item !== value);
}

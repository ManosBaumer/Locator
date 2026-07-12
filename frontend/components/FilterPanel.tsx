"use client";

import { ChainLogo } from "@/components/ChainLogo";
import { GlassCheckbox } from "@/components/GlassCheckbox";
import { GlassScrollArea } from "@/components/GlassScrollArea";
import { SITE_NAME } from "@/lib/site";
import type { Category, Chain } from "@/lib/types";
import type { HTMLAttributes } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

type Props = {
  categories: Category[];
  chains: Chain[];
  selectedCategories: string[];
  selectedChains: string[];
  defaultExpandAll?: boolean;
  variant?: "floating" | "bottom-sheet";
  dragHandleProps?: HTMLAttributes<HTMLElement>;
  isDragging?: boolean;
  onMinimize?: () => void;
  onHeaderHeight?: (height: number) => void;
  onCategoriesChange: (slugs: string[]) => void;
  onChainsChange: (slugs: string[]) => void;
};

export function FilterPanel({
  categories,
  chains,
  selectedCategories,
  selectedChains,
  defaultExpandAll = false,
  variant = "floating",
  dragHandleProps,
  isDragging = false,
  onMinimize,
  onHeaderHeight,
  onCategoriesChange,
  onChainsChange
}: Props) {
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(() => new Set());
  const [chainSearch, setChainSearch] = useState("");
  const headerRef = useRef<HTMLElement>(null);

  const normalizedSearch = chainSearch.trim().toLowerCase();

  function chainMatchesSearch(chain: Chain): boolean {
    if (!normalizedSearch) {
      return true;
    }

    return (
      chain.name.toLowerCase().includes(normalizedSearch) ||
      chain.slug.toLowerCase().includes(normalizedSearch)
    );
  }

  function chainsForCategory(categorySlug: string): Chain[] {
    return chains.filter(
      (chain) => chain.category_slug === categorySlug && chainMatchesSearch(chain)
    );
  }

  const hasSearchResults = useMemo(() => {
    if (!normalizedSearch) {
      return true;
    }

    return chains.some(chainMatchesSearch);
  }, [chains, normalizedSearch]);

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

  function handleCategoryToggle(categorySlug: string, checked: boolean) {
    const categoryChains = chains.filter((chain) => chain.category_slug === categorySlug);
    const categoryChainSlugs = categoryChains.map((chain) => chain.slug);

    if (checked) {
      onChainsChange([...new Set([...selectedChains, ...categoryChainSlugs])]);
      onCategoriesChange([...new Set([...selectedCategories, categorySlug])]);
      return;
    }

    onChainsChange(selectedChains.filter((slug) => !categoryChainSlugs.includes(slug)));
    onCategoriesChange(selectedCategories.filter((slug) => slug !== categorySlug));
  }

  const isBottomSheet = variant === "bottom-sheet";
  const selectedCount = selectedChains.length;
  const allChainSlugs = chains.map((chain) => chain.slug);
  const allSelected = allChainSlugs.length > 0 && selectedCount === allChainSlugs.length;

  function handleSelectAllToggle() {
    onChainsChange(allSelected ? [] : allChainSlugs);
  }

  useEffect(() => {
    if (!isBottomSheet || !onHeaderHeight) {
      return;
    }

    const header = headerRef.current;
    if (!header) {
      return;
    }

    const reportHeight = () => {
      onHeaderHeight(header.getBoundingClientRect().height);
    };

    reportHeight();
    const observer = new ResizeObserver(reportHeight);
    observer.observe(header);
    return () => observer.disconnect();
  }, [isBottomSheet, onHeaderHeight, selectedCount]);

  const selectionControls = (
    <div className="flex shrink-0 items-center gap-2">
      <button
        type="button"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={handleSelectAllToggle}
        className="rounded-full px-2 py-1 text-xs font-medium text-slate-600 transition hover:bg-white/35 hover:text-slate-900"
      >
        {allSelected ? "Deselect all" : "Select all"}
      </button>
      <span className="rounded-full bg-white/35 px-2.5 py-1 text-xs tabular-nums text-slate-600">
        {selectedCount} selected
      </span>
    </div>
  );

  const minimizeButton = onMinimize ? (
    <button
      type="button"
      aria-label="Minimize panel"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white/35 hover:text-slate-800"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={onMinimize}
    >
      <MinimizeIcon />
    </button>
  ) : null;

  return (
    <section
      className={`glass-panel grid min-h-0 overflow-hidden [text-shadow:0_1px_1px_rgba(255,255,255,0.6)] ${
        isBottomSheet
          ? "h-full grid-rows-[auto_auto_minmax(0,1fr)] rounded-t-[1.35rem] rounded-b-none border-b-0 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
          : "max-h-[calc(100dvh-2rem)] grid-rows-[auto_auto_minmax(0,1fr)] rounded-2xl"
      }`}
    >
      <header
        ref={isBottomSheet ? headerRef : undefined}
        className={`glass-panel-header shrink-0 px-3 ${
          isBottomSheet ? "rounded-t-[1.35rem] py-0" : "py-3"
        }`}
      >
        {isBottomSheet ? (
          <div className="flex w-full flex-col py-3">
            <div
              {...dragHandleProps}
              className={`bottom-sheet-grab flex w-full flex-col items-stretch ${dragHandleProps?.className ?? ""}`}
            >
              <span className="bottom-sheet-handle mx-auto shrink-0" aria-hidden="true" />
              <div className="min-h-5 w-full shrink-0" aria-hidden="true" />
            </div>
            <div className="flex w-full items-center justify-between gap-3 px-1">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-slate-500">
                {SITE_NAME}
              </p>
              {selectionControls}
            </div>
          </div>
        ) : (
          <div
            {...dragHandleProps}
            className={`flex touch-none select-none items-center justify-between gap-2 px-1 ${dragHandleProps?.className ?? ""} ${isDragging ? "cursor-grabbing" : dragHandleProps ? "cursor-grab" : ""}`}
          >
            {minimizeButton}
            {selectionControls}
          </div>
        )}
      </header>

      <div className="shrink-0 border-b border-white/35 px-3 py-2">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          <input
            type="search"
            value={chainSearch}
            onChange={(event) => setChainSearch(event.target.value)}
            placeholder="Search chains…"
            aria-label="Search chains"
            className="w-full rounded-xl border border-white/40 bg-white/25 py-2 pl-9 pr-8 text-sm text-slate-900 placeholder:text-slate-500 outline-none transition focus:border-sky-300/70 focus:bg-white/35"
          />
          {chainSearch ? (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setChainSearch("")}
              className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white/35 hover:text-slate-800"
            >
              <ClearIcon />
            </button>
          ) : null}
        </div>
      </div>

      <GlassScrollArea className="min-h-0">
        {!hasSearchResults ? (
          <p className="px-4 py-8 text-center text-sm text-slate-500">
            No chains match &ldquo;{chainSearch.trim()}&rdquo;
          </p>
        ) : (
        <div className="divide-y divide-slate-900/5">
          {categories.map((category) => {
            const categoryChains = chainsForCategory(category.slug);
            if (categoryChains.length === 0) {
              return null;
            }

            const allCategoryChains = chains.filter((chain) => chain.category_slug === category.slug);
            const expanded = normalizedSearch
              ? true
              : expandedCategories.has(category.slug);
            const selectedInCategory = allCategoryChains.filter((chain) =>
              selectedChains.includes(chain.slug)
            );
            const selectedStoreCount = selectedInCategory.reduce(
              (sum, chain) => sum + (chain.location_count ?? 0),
              0
            );
            const allSelected =
              allCategoryChains.length > 0 && selectedInCategory.length === allCategoryChains.length;
            const someSelected =
              selectedInCategory.length > 0 && selectedInCategory.length < allCategoryChains.length;

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

                  <div className="flex shrink-0 items-center gap-2 tabular-nums">
                    {normalizedSearch ? (
                      <span className="rounded-full bg-white/30 px-2 py-0.5 text-[11px] text-slate-600">
                        {categoryChains.length} match{categoryChains.length === 1 ? "" : "es"}
                      </span>
                    ) : (
                      <>
                        <span className="min-w-[2.25rem] text-right text-[11px] font-medium text-slate-600">
                          {selectedInCategory.length}/{allCategoryChains.length}
                        </span>
                        <span className="h-3 w-px shrink-0 bg-slate-900/10" aria-hidden="true" />
                        <span className="min-w-[2.5rem] text-right text-xs text-slate-500">
                          {selectedStoreCount.toLocaleString()}
                        </span>
                      </>
                    )}
                  </div>
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
        )}
      </GlassScrollArea>
    </section>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className={className} aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
      <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
    </svg>
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

"use client";

import { FilterPanel } from "@/components/FilterPanel";
import { Map } from "@/components/Map";
import { PanelRestoreTab } from "@/components/PanelRestoreTab";
import { loadCategories, loadChains } from "@/lib/static-data";
import { useDraggablePanel } from "@/lib/useDraggablePanel";
import type { Category, Chain } from "@/lib/types";
import { useEffect, useRef, useState } from "react";

const PANEL_MARGIN = 16;

export default function HomePage() {
  const panelRef = useRef<HTMLElement>(null);
  const { panelStyle, dragHandleProps, isDragging } = useDraggablePanel(panelRef, {
    margin: PANEL_MARGIN,
    initialPosition: { x: PANEL_MARGIN, y: PANEL_MARGIN }
  });
  const [isPanelMinimized, setIsPanelMinimized] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [chains, setChains] = useState<Chain[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedChains, setSelectedChains] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function loadFilters() {
      try {
        const [categoryRows, chainRows] = await Promise.all([loadCategories(), loadChains()]);
        setCategories(categoryRows);
        setChains(chainRows);
        const chainSlugs = chainRows.map((chain) => chain.slug);
        setSelectedChains(chainSlugs);
        setSelectedCategories(categoriesForChains(categoryRows, chainRows, chainSlugs));
        setLoadError(null);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Could not load filters");
      }
    }

    void loadFilters();
  }, []);

  function handleCategoriesChange(nextCategories: string[]) {
    const added = nextCategories.filter((slug) => !selectedCategories.includes(slug));
    const removed = selectedCategories.filter((slug) => !nextCategories.includes(slug));

    let nextChains = [...selectedChains];
    for (const categorySlug of added) {
      for (const chain of chains.filter((item) => item.category_slug === categorySlug)) {
        if (!nextChains.includes(chain.slug)) {
          nextChains.push(chain.slug);
        }
      }
    }
    for (const categorySlug of removed) {
      nextChains = nextChains.filter((slug) => {
        const chain = chains.find((item) => item.slug === slug);
        return !chain || chain.category_slug !== categorySlug;
      });
    }

    setSelectedCategories(nextCategories);
    setSelectedChains(nextChains);
  }

  function handleChainsChange(nextChains: string[]) {
    setSelectedChains(nextChains);
    setSelectedCategories(categoriesForChains(categories, chains, nextChains));
  }

  return (
    <main className="relative h-dvh w-full overflow-hidden">
      <Map selectedChains={selectedChains} />

      {isPanelMinimized ? (
        <PanelRestoreTab onRestore={() => setIsPanelMinimized(false)} />
      ) : null}

      <aside
        ref={panelRef}
        style={panelStyle}
        aria-hidden={isPanelMinimized}
        className={`absolute z-10 w-[min(22rem,calc(100vw-2rem))] transition-opacity duration-200 ${
          isPanelMinimized ? "pointer-events-none invisible opacity-0" : "opacity-100"
        }`}
      >
        {loadError ? (
          <div className="glass-panel rounded-2xl px-4 py-3 text-sm text-amber-950">
            {loadError}
          </div>
        ) : null}

        <FilterPanel
          categories={categories}
          chains={chains}
          selectedCategories={selectedCategories}
          selectedChains={selectedChains}
          dragHandleProps={dragHandleProps}
          isDragging={isDragging}
          onMinimize={() => setIsPanelMinimized(true)}
          onCategoriesChange={handleCategoriesChange}
          onChainsChange={handleChainsChange}
        />
      </aside>
    </main>
  );
}

function categoriesForChains(categories: Category[], chains: Chain[], selectedChains: string[]): string[] {
  return categories
    .filter((category) =>
      chains
        .filter((chain) => chain.category_slug === category.slug)
        .every((chain) => selectedChains.includes(chain.slug))
    )
    .map((category) => category.slug);
}

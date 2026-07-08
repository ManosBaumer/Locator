"use client";

import { FilterPanel } from "@/components/FilterPanel";
import { Map } from "@/components/Map";
import { getCategories, getChains } from "@/lib/api";
import type { Category, Chain } from "@/lib/types";
import { useEffect, useState } from "react";

export default function HomePage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [chains, setChains] = useState<Chain[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedChains, setSelectedChains] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    async function loadFilters() {
      try {
        const [categoryRows, chainRows] = await Promise.all([getCategories(), getChains()]);
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
    <main className="grid h-screen grid-cols-[360px_1fr] gap-4 p-4">
      <aside className="flex min-h-0 flex-col gap-4 overflow-auto">
        {loadError ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            {loadError}
          </div>
        ) : null}

        <FilterPanel
          categories={categories}
          chains={chains.filter(
            (chain) =>
              selectedCategories.length === 0 || selectedCategories.includes(chain.category_slug)
          )}
          selectedCategories={selectedCategories}
          selectedChains={selectedChains}
          onCategoriesChange={handleCategoriesChange}
          onChainsChange={handleChainsChange}
        />
      </aside>

      <Map selectedChains={selectedChains} />
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

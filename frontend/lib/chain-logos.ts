export const CHAIN_LOGO_SLUGS = [
  "hema",
  "rt-mart",
  "7-eleven",
  "aldi",
  "family-mart",
  "yonghui",
  "costco",
  "walmart",
  "mcdonalds",
  "kfc",
  "7fresh"
] as const;

export type ChainLogoSlug = (typeof CHAIN_LOGO_SLUGS)[number];

export const CHAIN_LABELS: Record<ChainLogoSlug, string> = {
  hema: "盒马 / Freshippo",
  "rt-mart": "大润发 / RT-Mart",
  "7-eleven": "7-Eleven / 7-11",
  aldi: "ALDI / 奥乐齐",
  "family-mart": "FamilyMart / 全家",
  yonghui: "永辉 / Yonghui",
  costco: "开市客 / Costco",
  walmart: "沃尔玛 / Walmart",
  mcdonalds: "麦当劳 / McDonald's",
  kfc: "肯德基 / KFC",
  "7fresh": "七鲜 / 7FRESH"
};

export function chainLabel(slug: string): string {
  if (isKnownChainLogo(slug)) {
    return CHAIN_LABELS[slug];
  }
  return slug;
}

export function chainLogoPath(slug: string): string {
  if (isKnownChainLogo(slug)) {
    return `/logos/${slug}.png`;
  }
  return "/logos/default.png";
}

export function chainMarkerPath(slug: string): string {
  if (isKnownChainLogo(slug)) {
    return `/logos/${slug}-marker.png`;
  }
  return "/logos/default.png";
}

export function chainImageId(slug: string): string {
  return `chain-${slug}`;
}

export function isKnownChainLogo(slug: string): slug is ChainLogoSlug {
  return (CHAIN_LOGO_SLUGS as readonly string[]).includes(slug);
}

export const CHAIN_ICON_IMAGE_EXPRESSION = [
  "match",
  ["get", "chain_slug"],
  "hema",
  "chain-hema",
  "rt-mart",
  "chain-rt-mart",
  "7-eleven",
  "chain-7-eleven",
  "aldi",
  "chain-aldi",
  "family-mart",
  "chain-family-mart",
  "yonghui",
  "chain-yonghui",
  "costco",
  "chain-costco",
  "walmart",
  "chain-walmart",
  "mcdonalds",
  "chain-mcdonalds",
  "kfc",
  "chain-kfc",
  "7fresh",
  "chain-7fresh",
  "chain-default"
] as const;

export async function loadChainMarkerImages(map: import("maplibre-gl").Map): Promise<void> {
  const slugs = [...CHAIN_LOGO_SLUGS, "default"] as const;

  await Promise.all(
    slugs.map(async (slug) => {
      const imageId = chainImageId(slug);
      if (map.hasImage(imageId)) {
        return;
      }

      const image = await loadImage(chainMarkerPath(slug));
      map.addImage(imageId, image, { pixelRatio: 2 });
    })
  );
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Failed to load chain logo: ${url}`));
    image.src = url;
  });
}

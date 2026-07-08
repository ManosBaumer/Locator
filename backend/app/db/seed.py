import asyncio

from sqlalchemy import select

from app.db.session import async_session
from app.models import Category, Chain

CATEGORY_DEFS = [
    {"name": "Supermarkets", "slug": "supermarket"},
    {"name": "Convenience Stores", "slug": "convenience"},
    {"name": "Fast Food", "slug": "fast-food"},
]

CHAINS = [
    {
        "slug": "hema",
        "name": "盒马 / Freshippo",
        "category_slug": "supermarket",
        "website": "https://www.freshippo.com/",
        "store_locator_url": "https://www.freshippo.com/",
    },
    {
        "slug": "rt-mart",
        "name": "大润发 / RT-Mart",
        "category_slug": "supermarket",
        "website": "https://www.rt-mart.com.cn/",
        "store_locator_url": (
            "https://www.rt-mart.com.cn/stores/store"
            "?size=8&memLiteClub=9&typeMarket=1&typeSuper=2&typeClub=5"
        ),
    },
    {
        "slug": "7-eleven",
        "name": "7-Eleven / 7-11",
        "category_slug": "convenience",
        "website": "https://www.7-11.cn/",
        "store_locator_url": "http://www.7-11cd.cn/shop/nearShop.aspx",
    },
    {
        "slug": "aldi",
        "name": "ALDI / 奥乐齐",
        "category_slug": "supermarket",
        "website": "https://www.aldi.cn/",
        "store_locator_url": "https://www.aldi.cn/ourshops/physicalstore/",
    },
    {
        "slug": "family-mart",
        "name": "FamilyMart / 全家",
        "category_slug": "convenience",
        "website": "https://www.familymart.com.cn/",
        "store_locator_url": "https://www.yidianlife.com/Family_Mart.html",
    },
    {
        "slug": "yonghui",
        "name": "永辉 / Yonghui",
        "category_slug": "supermarket",
        "website": "https://www.yonghuigroup.com/",
        "store_locator_url": "https://ccc.spdb.com.cn/miniSite/2228/cfb6e3d/yh.shtml",
    },
    {
        "slug": "costco",
        "name": "开市客 / Costco",
        "category_slug": "supermarket",
        "website": "https://www.costco.com.cn/",
        "store_locator_url": "https://www.costco.com.cn/",
    },
    {
        "slug": "walmart",
        "name": "沃尔玛 / Walmart",
        "category_slug": "supermarket",
        "website": "https://www.walmart.cn/",
        "store_locator_url": "https://www.samsclub.cn/shoplist",
    },
    {
        "slug": "mcdonalds",
        "name": "麦当劳 / McDonald's",
        "category_slug": "fast-food",
        "website": "https://www.mcdonalds.com.cn/",
        "store_locator_url": "https://www.mcdonalds.com.cn/store",
    },
    {
        "slug": "kfc",
        "name": "肯德基 / KFC",
        "category_slug": "fast-food",
        "website": "https://www.kfc.com.cn/",
        "store_locator_url": "https://www.kfc.com.cn/kfccda/ashx/GetStoreList.ashx?op=cname",
    },
    {
        "slug": "7fresh",
        "name": "七鲜 / 7FRESH",
        "category_slug": "supermarket",
        "website": "https://www.7fresh.com/",
        "store_locator_url": "https://www.7fresh.com/super-market",
    },
]


async def seed() -> None:
    async with async_session() as session:
        categories_by_slug: dict[str, Category] = {}
        for category_data in CATEGORY_DEFS:
            category = await session.scalar(
                select(Category).where(Category.slug == category_data["slug"])
            )
            if category is None:
                category = Category(**category_data)
                session.add(category)
                await session.flush()
            categories_by_slug[category_data["slug"]] = category

        for chain_data in CHAINS:
            category_slug = chain_data.pop("category_slug")
            category = categories_by_slug[category_slug]
            chain = await session.scalar(select(Chain).where(Chain.slug == chain_data["slug"]))
            if chain is None:
                session.add(Chain(category_id=category.id, country="CN", **chain_data))
            else:
                chain.category_id = category.id

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())

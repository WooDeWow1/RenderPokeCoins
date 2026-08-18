"""Rewrite product image_url values from the Emergent CDN to local /images/... paths."""
import asyncio
import os
import pathlib
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

CDN_PREFIX = "https://static.prod-images.emergentagent.com"

HASH_TO_LOCAL = {
    "3ab05ddaf8a485b60bf1084d4dba78ab7108f82619fa73b9abc772ff7bb7068c": "/images/snorlax.jpg",
    "d51e3620405fffdaa6274f243f8be4dcb033aecf285738dfb12c097e13f28205": "/images/gengar.jpg",
    "a1cb3e2f61373eebc47314154e840108ff51e22f6b3e2445e1d251e47e96c67c": "/images/psyduck.jpg",
    "b5567f7be5ab8efdf0eb610e39a8c24853b614f342cc5b99c25a7c46a759343a": "/images/coins-stack.jpg",
    "0c5cba41f0c264d1d048fefa4e9bdbf766fc60fa86bb591d83e3f2c8fd7e96e2": "/images/event-pass.jpg",
    "7b6169728db891ad39928b62dcd6c8d71d90bf729363109f5bf1314dc20af698": "/images/platinum-medal.jpg",
    "c8ad17cbe0d213c6c2da362c18d24221a0c2ea48e22daa9a6766b21c81d3e8c4": "/images/platinum-medal-set.jpg",
}

CATEGORY_FALLBACK = {
    "pokecoin_bundle": "/images/coins-stack.jpg",
    "event_pass": "/images/event-pass.jpg",
    "medals": "/images/platinum-medal.jpg",
    "shundo_service": "/images/psyduck.jpg",
}

LOCAL_DIR = pathlib.Path("/app/frontend/public/images")


def local_path_for(url: str, category: str) -> str:
    for digest, local in HASH_TO_LOCAL.items():
        if digest in url:
            return local
    return CATEGORY_FALLBACK.get(category, "/images/coins-stack.jpg")


async def main():
    missing = [p for p in HASH_TO_LOCAL.values() if not (LOCAL_DIR / p.split("/")[-1]).exists()]
    if missing:
        raise SystemExit(f"Run download_images.py first, missing: {missing}")

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    updated = 0
    async for product in db.products.find({}):
        url = product.get("image_url") or ""
        if url.startswith("/images/"):
            continue
        new_url = local_path_for(url, product.get("category", ""))
        await db.products.update_one({"_id": product["_id"]}, {"$set": {"image_url": new_url}})
        print(f"{product['name']}: {url or '(empty)'} -> {new_url}")
        updated += 1
    print(f"Updated {updated} product(s).")


asyncio.run(main())

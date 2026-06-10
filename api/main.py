# api/main.py
# ══════════════════════════════════════════════════════════════════════════════
#  Dashboard API — Generic版
#
#  ✅ নতুন website scrape করতে শুধু নিচের SCRAPER CONFIG section পরিবর্তন করুন।
#  ✅ অন্য কোনো জায়গা পরিবর্তন করতে হবে না।
# ══════════════════════════════════════════════════════════════════════════════

import asyncio, os, sys
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_pool, close_pool
from db.queries import run_migrations, save_profiles, save_failed_urls
from exports.exporter import save_json, save_csv, save_xml, save_failures


# ══════════════════════════════════════════════════════════════════════════════
#  ✏️  SCRAPER CONFIG — নতুন website এর জন্য এখানে পরিবর্তন করুন
# ══════════════════════════════════════════════════════════════════════════════

# আপনার scraper file থেকে এই দুটো function import করুন:
#   collect_profile_urls(page, client) → List[str]
#   scrape_profile(url, client)        → CompanyProfile | None
#
# উদাহরণ (minimo):
from scrapers.minimo_scraper import collect_profile_urls_from_page as collect_profile_urls
from scrapers.minimo_scraper import scrape_profile
#
# উদাহরণ (নতুন scraper):
# from scrapers.rakuten_scraper import collect_profile_urls, scrape_profile

# ══════════════════════════════════════════════════════════════════════════════
#  ここから下は変更不要 — Do not edit below this line
# ══════════════════════════════════════════════════════════════════════════════

scraper_state = {
    "status": "idle", "total": 0, "success": 0, "failed": 0, "skipped": 0,
    "current_url": "", "speed": 0.0, "eta": None, "start_time": None, "logs": [],
}
active_connections: list[WebSocket] = []
_scraped_urls:  set  = set()
_all_profiles:  list = []
_all_failures:  list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    await _load_scraped_urls_from_db()
    yield
    await close_pool()


async def _load_scraped_urls_from_db():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT source_url FROM company_list WHERE source_url IS NOT NULL"
            )
            for row in rows:
                _scraped_urls.add(row["source_url"])
        if _scraped_urls:
            add_log(f"Loaded {len(_scraped_urls)} already-scraped URLs from DB")
    except Exception as e:
        add_log(f"Could not load scraped URLs: {e}", "WARNING")


app = FastAPI(title="Scraper Dashboard API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


async def broadcast(data: dict):
    dead = []
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        active_connections.remove(ws)


def add_log(msg: str, level: str = "INFO"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "msg": msg}
    scraper_state["logs"].append(entry)
    if len(scraper_state["logs"]) > 300:
        scraper_state["logs"] = scraper_state["logs"][-300:]
    return entry


async def _save_all_results(profiles: list, failures: list, db_enabled: bool):
    if not profiles and not failures:
        return
    add_log(f"Saving {len(profiles)} profiles, {len(failures)} failures...")
    if profiles:
        save_json(profiles)
        save_csv(profiles)
        save_xml(profiles)
        add_log(f"Saved JSON / CSV / XML ({len(profiles)} records)")
    if failures:
        save_failures(failures)
    if db_enabled:
        try:
            if profiles:
                await save_profiles(profiles)
                add_log(f"Saved {len(profiles)} profiles to PostgreSQL")
            if failures:
                await save_failed_urls(failures)
        except Exception as e:
            add_log(f"DB save error: {e}", "ERROR")


async def run_scraper_job(config: dict):
    global _all_profiles, _all_failures

    scraper_state.update({
        "status": "running",
        "total": 0, "success": 0, "failed": 0, "skipped": 0,
        "current_url": "", "start_time": datetime.now().isoformat(), "eta": None,
    })
    await broadcast({"type": "state", "data": scraper_state})

    session_profiles, session_failures = [], []

    try:
        import httpx, random
        from models.scraped_item import FailedURL
        from utils.user_agents import get_weighted_ua

        page_start = int(config.get("page_start", 1))
        page_end   = int(config.get("page_end", 100))
        workers    = int(config.get("workers", 2))
        db_enabled = config.get("db_enabled", True)

        async with httpx.AsyncClient(
            headers={"User-Agent": get_weighted_ua()},
            timeout=30, follow_redirects=True
        ) as client:

            # ── Step 1: URL collection ───────────────────────────────────
            all_urls, seen = [], set()
            for page in range(page_start, page_end + 1):
                if scraper_state["status"] == "stopping":
                    break
                urls = await collect_profile_urls(page, client)
                if not urls:
                    add_log(f"Page {page}: no data — stopped")
                    await broadcast({"type": "state", "data": scraper_state})
                    break
                for u in urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
                add_log(f"Page {page}: {len(urls)} URLs (total {len(all_urls)})")
                await broadcast({"type": "state", "data": scraper_state})
                await asyncio.sleep(1.5)

            # ── Step 2: Skip already-scraped URLs (duplicate prevention) ─
            pending = [u for u in all_urls if u not in _scraped_urls]
            skipped = len(all_urls) - len(pending)

            scraper_state["total"]   = len(pending)
            scraper_state["skipped"] = skipped
            add_log(f"Total: {len(all_urls)} | Done: {skipped} | Pending: {len(pending)}")
            await broadcast({"type": "state", "data": scraper_state})

            if not pending:
                add_log("Nothing new to scrape!", "WARNING")
                scraper_state["status"] = "done"
                await broadcast({"type": "state", "data": scraper_state})
                return

            # ── Step 3: Scrape each URL ──────────────────────────────────
            sem        = asyncio.Semaphore(workers)
            start_ts   = asyncio.get_event_loop().time()
            done_count = 0

            async def scrape_one(url: str):
                nonlocal done_count
                async with sem:
                    if scraper_state["status"] == "stopping":
                        scraper_state["skipped"] += 1
                        return
                    scraper_state["current_url"] = url
                    await asyncio.sleep(random.uniform(2, 5))
                    log_e = None
                    try:
                        p = await scrape_profile(url, client)
                        if p:
                            session_profiles.append(p)
                            _all_profiles.append(p)
                            _scraped_urls.add(url)
                            scraper_state["success"] += 1
                            log_e = add_log(
                                f"✓ {p.name or url} | {p.prefecture or '-'} | "
                                f"備考:{p.biko or '-'} | Tel1:{p.tel1 or '-'}"
                            )
                        else:
                            raise ValueError("scrape_profile returned None")
                    except Exception as exc:
                        f = FailedURL(
                            url=url, error_type=type(exc).__name__,
                            message=str(exc)[:200], scraper_name="scraper"
                        )
                        session_failures.append(f)
                        _all_failures.append(f)
                        scraper_state["failed"] += 1
                        log_e = add_log(f"✗ {url} — {str(exc)[:80]}", "ERROR")
                    finally:
                        done_count += 1
                        elapsed   = asyncio.get_event_loop().time() - start_ts
                        speed     = done_count / elapsed * 60 if elapsed > 0 else 0
                        remaining = scraper_state["total"] - done_count
                        eta = round(remaining / (done_count / elapsed)) if done_count > 0 else None
                        scraper_state["speed"] = round(speed, 1)
                        scraper_state["eta"]   = eta
                        await broadcast({"type": "state", "data": scraper_state})
                        if log_e:
                            await broadcast({"type": "log", "data": log_e})

            await asyncio.gather(*[scrape_one(u) for u in pending])

        # ── Step 4: Save ─────────────────────────────────────────────────
        await _save_all_results(session_profiles, session_failures, db_enabled)
        final = "done" if scraper_state["status"] != "stopping" else "idle"
        scraper_state["status"] = final
        add_log(
            f"{'Complete' if final == 'done' else 'Stopped'} — "
            f"{scraper_state['success']} ok, "
            f"{scraper_state['failed']} failed, "
            f"{scraper_state['skipped']} skipped"
        )
        await broadcast({"type": "state", "data": scraper_state})

    except Exception as exc:
        await _save_all_results(session_profiles, session_failures,
                                config.get("db_enabled", True))
        scraper_state["status"] = "idle"
        add_log(f"Fatal: {exc}", "ERROR")
        await broadcast({"type": "state", "data": scraper_state})


class StartConfig(BaseModel):
    page_start:    int  = 1
    page_end:      int  = 100
    workers:       int  = 2
    db_enabled:    bool = True
    proxy_enabled: bool = False


@app.post("/api/scraper/start")
async def start_scraper(config: StartConfig):
    if scraper_state["status"] == "running":
        return {"ok": False, "msg": "Already running"}
    asyncio.create_task(run_scraper_job(config.model_dump()))
    return {"ok": True}


@app.post("/api/scraper/stop")
async def stop_scraper():
    if scraper_state["status"] != "running":
        return {"ok": False, "msg": "Not running"}
    scraper_state["status"] = "stopping"
    add_log("Stop requested — saving data...", "WARNING")
    await broadcast({"type": "state", "data": scraper_state})
    return {"ok": True}


@app.post("/api/scraper/reset")
async def reset_scraper():
    global _all_profiles, _all_failures
    _scraped_urls.clear()
    _all_profiles.clear()
    _all_failures.clear()
    add_log("Reset: memory cleared — next Start will re-scrape all", "WARNING")
    await broadcast({"type": "state", "data": scraper_state})
    return {"ok": True}


@app.get("/api/scraper/status")
async def get_status():
    return {**scraper_state, "scraped_count": len(_scraped_urls)}


@app.get("/api/data/profiles")
async def get_profiles(limit: int = 200, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows  = await conn.fetch(
            "SELECT * FROM company_list ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM company_list")
    return {"total": total, "rows": [dict(r) for r in rows]}


@app.get("/api/data/failed")
async def get_failed(limit: int = 100):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM failed_urls ORDER BY failed_at DESC LIMIT $1", limit
        )
    return {"rows": [dict(r) for r in rows]}


@app.get("/api/export/{fmt}")
async def export_file(fmt: str):
    files = {"json": "result.json", "csv": "result.csv", "xml": "result.xml"}
    if fmt not in files:
        return {"error": "Invalid format"}
    if not os.path.exists(files[fmt]):
        return {"error": "File not found — run scraper first"}
    return FileResponse(files[fmt], filename=files[fmt])


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    await ws.send_json({"type": "state", "data": scraper_state})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in active_connections:
            active_connections.remove(ws)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)

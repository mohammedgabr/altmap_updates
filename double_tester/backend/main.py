import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import threading
import os
from mimic_engine import MimicEngine, find_templates

# --- DASHBOARD API (Port 5000) ---
app = FastAPI(title="Double Tester API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
active_engine: Optional[MimicEngine] = None
logs: List[dict] = []
TEMPLATE_DIRS = ["../../upstream", "../../altmap_verified"]
cached_templates: List[dict] = []

def load_templates_into_cache():
    global cached_templates
    print("🔄 Loading templates into cache...")
    new_templates = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for d in TEMPLATE_DIRS:
        full_dir = os.path.join(base_dir, d)
        if os.path.exists(full_dir):
            new_templates.extend(find_templates(full_dir))
    cached_templates = new_templates
    print(f"✅ Loaded {len(cached_templates)} templates.")

@app.on_event("startup")
async def startup_event():
    # Load templates in a background thread to not block startup if needed,
    # but for simplicity here we just call it.
    load_templates_into_cache()

@app.get("/templates")
async def get_templates(q: Optional[str] = None):
    if not q:
        # Return top 50 by default to avoid crashing browser
        return cached_templates[:50]
    
    q = q.lower()
    results = []
    for t in cached_templates:
        if q in t["id"].lower() or q in t["name"].lower() or q in os.path.basename(t["path"]).lower():
            results.append(t)
            if len(results) >= 50: # Limit to top 50
                break
    return results

@app.get("/templates/direct")
async def get_template_direct(path: str):
    # Try to find it in cache first
    for t in cached_templates:
        if t["path"] == path or os.path.basename(t["path"]) == path:
            return t
    
    # If not in cache, try to load it specifically (if it exists)
    if os.path.exists(path):
        from mimic_engine import find_templates
        dir_name = os.path.dirname(path)
        base_name = os.path.basename(path)
        # Note: find_templates returns a list, we just need one
        found = find_templates(dir_name)
        for f in found:
            if f["path"] == path:
                return f
    
    return {"error": "Template not found"}

@app.post("/templates/refresh")
async def refresh_templates():
    load_templates_into_cache()
    return {"status": "success", "count": len(cached_templates)}

@app.post("/activate")
async def activate_template(template_path: str):
    global active_engine
    try:
        active_engine = MimicEngine(template_path)
        return {"status": "success", "template_id": active_engine.template_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/logs")
async def get_logs():
    return logs

@app.post("/reset")
async def reset_engine():
    global active_engine, logs
    if active_engine:
        active_engine.reset()
    logs = []
    return {"status": "reset"}

# --- MIMIC SERVER (Port 5001) ---
mimic_app = FastAPI(title="Mimic Target Server")

@mimic_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def catch_all(request: Request, path: str):
    global active_engine, logs
    
    method = request.method
    full_path = f"/{path}"
    
    log_entry = {
        "method": method,
        "path": full_path,
        "timestamp": uvicorn.main.time.time() if hasattr(uvicorn.main, "time") else 0,
        "matched": False
    }

    if not active_engine:
        log_entry["response"] = "No active template"
        logs.append(log_entry)
        return "No active template. Please select one from the dashboard."

    result = active_engine.process_request(method, full_path)
    
    log_entry["matched"] = result["status"] == 200
    log_entry["response"] = result["content"]
    logs.append(log_entry)
    
    # Keep logs small
    if len(logs) > 100:
        logs.pop(0)

    if result["status"] == 200:
        from fastapi.responses import Response
        return Response(content=result["content"], media_type="text/plain")
    
    raise HTTPException(status_code=result["status"], detail=result["content"])

def run_mimic():
    uvicorn.run(mimic_app, host="0.0.0.0", port=5001)

def run_dashboard():
    uvicorn.run(app, host="0.0.0.0", port=5000)

if __name__ == "__main__":
    # Start Mimic Server in a separate thread
    threading.Thread(target=run_mimic, daemon=True).start()
    # Start Dashboard API
    run_dashboard()

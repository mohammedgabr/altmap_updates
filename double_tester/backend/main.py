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

@app.get("/templates")
async def get_templates():
    all_templates = []
    # Resolve paths relative to this script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for d in TEMPLATE_DIRS:
        full_dir = os.path.join(base_dir, d)
        if os.path.exists(full_dir):
            all_templates.extend(find_templates(full_dir))
    return all_templates

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

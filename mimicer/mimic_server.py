#!/usr/bin/env python3
import os
import sys
import json
import argparse
import threading
import subprocess
import shutil
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

class MimicHandler(BaseHTTPRequestHandler):
    routes = []
    template_id = ""

    def log_message(self, format, *args):
        # Print beautiful logs to stdout
        sys.stdout.write(f"[{self.template_id}] - - [{self.log_date_time_string()}] {format % args}\n")

    def do_request(self, method):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path
        
        # 1. Try matching with full path + query string
        matched_route = None
        for r in self.routes:
            if r.get('method') == method:
                # Direct match clean path or match with query string
                if r.get('path') == self.path or r.get('path') == clean_path:
                    matched_route = r
                    break
        
        # 2. Try prefix/contains fallback or case-insensitive matching
        if not matched_route:
            for r in self.routes:
                if r.get('method') == method:
                    # e.g., if template path is sub-segment
                    t_path = r.get('path')
                    if clean_path.endswith(t_path) or t_path.endswith(clean_path):
                        matched_route = r
                        break

        # 3. Fallback: match clean path ignoring method
        if not matched_route:
            for r in self.routes:
                if r.get('path') == clean_path:
                    matched_route = r
                    break

        if matched_route:
            status = matched_route.get('status', 200)
            headers = matched_route.get('headers', {})
            body = matched_route.get('body', "Mock Mimic positive response")
            
            # If body is dictionary/json, serialize it
            if isinstance(body, (dict, list)):
                body = json.dumps(body)
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/json"
                    
            body_bytes = body.encode('utf-8') if isinstance(body, str) else body
            
            self.send_response(status)
            for h_name, h_val in headers.items():
                self.send_header(h_name, h_val)
            self.send_header('Content-Length', str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            
            print(f"[+] [HIT] {method} {self.path} -> Replied with HTTP {status} (Satisfies Matchers)")
        else:
            # Route not found
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            err_resp = {
                "error": "Route not matched in mimic server",
                "request": {
                    "method": method,
                    "path": self.path,
                    "clean_path": clean_path
                },
                "registered_routes": [
                    {"method": r.get('method'), "path": r.get('path')} for r in self.routes
                ]
            }
            self.wfile.write(json.dumps(err_resp, indent=4).encode('utf-8'))
            print(f"[-] [MISS] {method} {self.path} -> 404 Route Not Registered")

    def do_GET(self):
        self.do_request("GET")
        
    def do_POST(self):
        self.do_request("POST")
        
    def do_PUT(self):
        self.do_request("PUT")
        
    def do_DELETE(self):
        self.do_request("DELETE")
        
    def do_HEAD(self):
        self.do_request("HEAD")
        
    def do_OPTIONS(self):
        self.do_request("OPTIONS")

def main():
    parser = argparse.ArgumentParser(description="Mock Mimic Server for Nuclei Template Testing")
    parser.path_or_id = parser.add_argument('config', help="Path to template.conf or template ID (e.g. CVE-2001-0537)")
    parser.add_argument('--port', type=int, default=80, help="Port to run server on (default: 80)")
    parser.add_argument('--host', default="0.0.0.0", help="Host address to bind to (default: 0.0.0.0)")
    parser.add_argument('--verify', help="Run nuclei verification against target (e.g. http://127.0.0.1)", metavar="TARGET_URL")
    args = parser.parse_args()
    
    config_path = args.config
    
    # If the user passed template ID instead of filepath, find it automatically
    workspace_dir = "../"
    if not os.path.exists(config_path):
        potential_path = os.path.join(workspace_dir, "mimicer", "mimic_confs", config_path, "template.conf")
        if os.path.exists(potential_path):
            config_path = potential_path
            
    if not os.path.exists(config_path):
        print(f"[-] Configuration file not found: {args.config}")
        sys.exit(1)
        
    print(f"[*] Loading mimic configuration: {config_path}")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            conf_data = json.load(f)
    except Exception as e:
        print(f"[-] Error loading configuration: {e}")
        sys.exit(1)
        
    MimicHandler.routes = conf_data.get('routes', [])
    MimicHandler.template_id = conf_data.get('template_id', 'mimic-server')
    
    print(f"[+] Loaded {len(MimicHandler.routes)} route(s) for template: {MimicHandler.template_id}")
    for idx, r in enumerate(MimicHandler.routes, 1):
        print(f"    Route #{idx}: {r.get('method')} {r.get('path')} (Status {r.get('status')})")
        
    server = HTTPServer((args.host, args.port), MimicHandler)
    
    if args.verify:
        target_url = args.verify
        print(f"\n[+] Starting Mimic Server in background on http://{args.host}:{args.port}...")
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        # Wait a moment for server to start
        time.sleep(1)
        
        template_id = MimicHandler.template_id
        print(f"\n[*] Running verification: nuclei -u {target_url} -id {template_id}")
        
        cmd = ["nuclei", "-u", target_url, "-id", template_id]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        output = result.stdout + result.stderr
        print(output)
        
        template_src = os.path.join(workspace_dir, conf_data.get('template_path', ''))
        template_filename = os.path.basename(template_src)
        
        if "1 matches found" in output:
            print("\n[+] Verification SUCCESS: 1 matches found!")
            dest_dir = os.path.join(workspace_dir, "mimicer", "working_mimics")
        else:
            print("\n[-] Verification FAILED: Match not found.")
            dest_dir = os.path.join(workspace_dir, "mimicer", "failed_mimics")
            
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, template_filename)
        
        if os.path.exists(template_src):
            shutil.copy(template_src, dest_path)
            print(f"[*] Copied template to {dest_path}")
        else:
            print(f"[-] Source template file not found: {template_src}")
            
        print("\n[*] Stopping Mimic Server...")
        server.shutdown()
        server_thread.join()
        print("[+] Verification complete.")
        
    else:
        print(f"\n[+] Starting Mimic Server on http://{args.host}:{args.port}...")
        print("[*] Press Ctrl+C to terminate the server.\n")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Stopping Mimic Server...")
            server.server_close()
            print("[+] Mimic Server stopped.")

if __name__ == "__main__":
    main()

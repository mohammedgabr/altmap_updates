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

# Resolve nuclei binary - check shutil.which and common install paths
def find_nuclei():
    import shutil as _shutil
    found = _shutil.which("nuclei")
    if found:
        return found
    common_paths = [
        os.path.expanduser("~/go/bin/nuclei"),
        "/usr/local/bin/nuclei",
        "/usr/bin/nuclei",
        "/root/go/bin/nuclei",
        "/home/go/bin/nuclei",
    ]
    for p in common_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return "nuclei"  # fallback, will error clearly if missing

NUCLEI_BIN = find_nuclei()

class MimicHandler(BaseHTTPRequestHandler):
    routes = []
    template_id = ""

    def log_message(self, format, *args):
        # Print beautiful logs to stdout
        sys.stdout.write(f"[{self.template_id}] - - [{self.log_date_time_string()}] {format % args}\n")

    @staticmethod
    def normalize_path(path):
        """Normalize a request path+query so that empty params match with or without trailing =.
        e.g. ?search= and ?search both normalize to ?search"""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(path)
        # Re-encode query params, dropping empty values' trailing =
        params = parse_qs(parsed.query, keep_blank_values=True)
        normalized_query = urlencode(sorted(params.items()))
        return urlunparse(parsed._replace(query=normalized_query))

    def do_request(self, method):
        parsed_url = urlparse(self.path)
        clean_path = parsed_url.path
        norm_path = self.normalize_path(self.path)
        
        # 1. Try matching with full path + query string (exact or normalized)
        matched_route = None
        for r in self.routes:
            if r.get('method') == method:
                r_path = r.get('path', '')
                if r_path == self.path or r_path == clean_path or \
                   self.normalize_path(r_path) == norm_path:
                    matched_route = r
                    break
        
        # 2. Try prefix/contains fallback or case-insensitive matching
        if not matched_route:
            for r in self.routes:
                if r.get('method') == method:
                    t_path = r.get('path', '')
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
        
        # Check if a YAML template file exists inside the conf folder
        conf_folder = os.path.dirname(os.path.abspath(config_path))
        yaml_in_conf = None
        for fname in os.listdir(conf_folder):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                yaml_in_conf = os.path.join(conf_folder, fname)
                break
        
        if yaml_in_conf:
            print(f"\n[*] Running verification: {NUCLEI_BIN} -u {target_url} --template {yaml_in_conf}")
            cmd = [NUCLEI_BIN, "-u", target_url, "--template", yaml_in_conf]
        else:
            print(f"\n[*] Running verification: {NUCLEI_BIN} -u {target_url} -id {template_id}")
            cmd = [NUCLEI_BIN, "-u", target_url, "-id", template_id]
        
        # Pass enriched PATH so go binaries are found even in restricted envs
        env = os.environ.copy()
        env["PATH"] = ":".join([
            os.path.expanduser("~/go/bin"),
            "/usr/local/go/bin",
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
            env.get("PATH", ""),
        ])
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        output = result.stdout + result.stderr
        print(output)
        
        # Determine destination name from the already-resolved conf_folder
        conf_folder_name = os.path.basename(conf_folder)
        

        # Always anchor dest_base relative to mimicer script dir, not conf_folder parent
        # This avoids src==dst when conf is already in working_mimics or failed_mimics
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if "1 matches found" in output:
            print("\n[+] Verification SUCCESS: 1 matches found!")
            dest_base = os.path.join(script_dir, "working_mimics")
        else:
            print("\n[-] Verification FAILED: Match not found.")
            dest_base = os.path.join(script_dir, "failed_mimics")
            
        dest_base = os.path.abspath(dest_base)
        os.makedirs(dest_base, exist_ok=True)
        dest_path = os.path.join(dest_base, conf_folder_name)
        
        conf_folder_abs = os.path.abspath(conf_folder)
        if conf_folder_abs == dest_path:
            print(f"[*] Conf folder already at correct destination: {dest_path}")
        else:
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.move(conf_folder_abs, dest_path)
            print(f"[*] Moved conf folder to {dest_path}")
            
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

#!/usr/bin/env python3
import os
import sys
import csv
import re
import yaml
import json

def clean_path(path_str):
    # Remove {{BaseURL}}, {{Hostname}}, etc.
    cleaned = re.sub(r'\{\{[a-zA-Z0-9_]+\}\}', '', path_str)
    # Ensure it starts with /
    if not cleaned.startswith('/'):
        cleaned = '/' + cleaned
    # Collapse multiple slashes
    cleaned = re.sub(r'/+', '/', cleaned)
    # Strip trailing wildcard * (nuclei uses these as glob, not literal)
    cleaned = cleaned.rstrip('*').rstrip('?')
    return cleaned

DSL_VAR_RE = re.compile(r'\{\{.+?\}\}')

def is_static_word(word):
    """Return False if the word contains nuclei DSL expressions like {{md5(num)}} that
    can never be matched statically."""
    return not DSL_VAR_RE.search(word)

def generate_matching_string(regex_pattern):
    # Generates a simple text satisfying basic regex patterns commonly found in templates
    # e.g., "[0-9]{1,2}.[0-9]{1,2}.[0-9]{1,2}-MariaDB" -> "10.5.12-MariaDB"
    # or "root:[x*]:0:0:" -> "root:x:0:0:"
    
    # Let's perform some heuristic replacements
    gen = regex_pattern
    # [0-9]{1,2} -> 10
    gen = re.sub(r'\[0-9\]\{[0-9]+,[0-9]+\}', '10', gen)
    gen = re.sub(r'\\d\{[0-9]+,[0-9]+\}', '10', gen)
    gen = re.sub(r'\[0-9\]\+', '123', gen)
    gen = re.sub(r'\\d\+', '123', gen)
    # [A-Za-z0-9=]+ -> dummybase64
    gen = re.sub(r'\[[A-Za-z0-9=+_-]+\]\+', 'dummy_value', gen)
    # Simplify regex groups
    gen = gen.replace('\\.', '.')
    gen = gen.replace('\\/', '/')
    gen = gen.replace('\\-', '-')
    gen = gen.replace('root:[x*]:0:0:', 'root:x:0:0:')
    # Strip regex boundary anchors
    gen = gen.lstrip('^').rstrip('$')
    # If it's still got complex regex chars, return a fallback or clean it
    gen = re.sub(r'[\(\)\|\[\]\*\+\?\{\}]', '', gen)
    return gen

def parse_template(yaml_path):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def find_template_path(template_id, csv_path):
    if not os.path.exists(csv_path):
        print(f"[-] CSV file not found: {csv_path}")
        return None
        
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 2:
                continue
            if row[0].strip() == template_id:
                rel_path = row[1].strip()
                # Check directly, then under upstream/
                paths_to_try = [
                    rel_path,
                    os.path.join("upstream", rel_path),
                    os.path.join("../", rel_path),
                    os.path.join("../upstream", rel_path)
                ]
                for p in paths_to_try:
                    if os.path.exists(p):
                        return p
    return None

def process_template(template_id, auto_mode, workspace_dir, csv_path):
    print(f"[*] Looking for template {template_id}...")
    yaml_path = find_template_path(template_id, csv_path)
    if not yaml_path:
        # Let's search inside upstream folder recursively as a fallback
        print(f"[-] Could not find in unverified.csv. Searching recursively in upstream...")
        found = False
        for root, dirs, files in os.walk(os.path.join(workspace_dir, "upstream")):
            for file in files:
                if file == f"{template_id}.yaml":
                    yaml_path = os.path.join(root, file)
                    found = True
                    break
            if found:
                break
                
    if not yaml_path or not os.path.exists(yaml_path):
        print(f"[-] Template {template_id} not found in repository.")
        return
        
    print(f"[+] Found template at: {yaml_path}")
    
    try:
        template = parse_template(yaml_path)
    except Exception as e:
        print(f"[-] Error parsing YAML: {e}")
        return
        
    http_blocks = template.get('http', [])
    if not http_blocks:
        print("[-] No HTTP requests/blocks found in this template. Only HTTP templates are supported.")
        return
        
    routes = []
    
    # Process each HTTP request in the block
    # Note: Nuclei can have multiple requests under one http block, or multiple http blocks.
    req_index = 0
    for block in http_blocks:
        # Check raw requests
        raw_requests = block.get('raw', [])
        # Check normal path requests
        paths = block.get('path', [])
        # Extract methods/headers/bodies if normal paths
        method = block.get('method', 'GET')
        
        # Setup defaults
        matchers = block.get('matchers', [])
        extractors = block.get('extractors', [])
        matchers_cond = block.get('matchers-condition', 'or')
        
        # Determine status code to reply with
        status_code = 200
        for m in matchers:
            if m.get('type') == 'status':
                status_list = m.get('status', [200])
                if status_list:
                    status_code = status_list[0]
                    
        # Word and Regex matching to auto-satisfy
        body_parts = []
        headers = {"Content-Type": "text/html"}
        
        # Handle matchers
        for m in matchers:
            m_type = m.get('type')
            m_part = m.get('part', 'body')
            
            if m_type == 'word':
                words = m.get('words') or []
                if m_part in ('body', ''):
                    # Skip words with unresolvable DSL expressions
                    body_parts.extend(w for w in words if is_static_word(w))
                elif m_part == 'header':
                    for w in words:
                        if ':' in w:
                            h_name, h_val = w.split(':', 1)
                            headers[h_name.strip()] = h_val.strip()
                        else:
                            headers[w] = "true"
                elif m_part == 'content_type':
                    # Set the Content-Type header to satisfy this matcher
                    for w in words:
                        headers['Content-Type'] = w
                        break
                elif m_part in ('set_cookie', 'cookie'):
                    # Inject a Set-Cookie header
                    for w in words:
                        headers['Set-Cookie'] = w
                        break
                elif m_part in ('location', 'redirect_location'):
                    for w in words:
                        headers['Location'] = w
                        break
                else:
                    # Unknown part — inject as a generic header so it appears somewhere
                    for w in words:
                        headers[f'X-Mimic-{m_part.title()}'] = w
                        break
            elif m_type == 'regex':
                regexes = m.get('regex') or []
                if m_part == 'body' or m_part == '':
                    for rx in regexes:
                        body_parts.append(generate_matching_string(rx))
                elif m_part == 'header':
                    for rx in regexes:
                        headers["X-Regex-Matched"] = generate_matching_string(rx)
            elif m_type == 'dsl':
                dsl_exprs = m.get('dsl') or []
                for expr in dsl_exprs:
                    # Simple DSL parser to inject words/status
                    # e.g., contains(body, "admin")
                    matches = re.findall(r'contains\((body|header|all), ["\'](.*?)["\']\)', expr)
                    for part, val in matches:
                        if part == 'body':
                            body_parts.append(val)
                        elif part == 'header':
                            headers["X-DSL-Matched"] = val
                    # status_code == 200
                    status_match = re.search(r'status_code\s*==\s*([0-9]+)', expr)
                    if status_match:
                        status_code = int(status_match.group(1))
                        
        # Handle extractors to ensure positive extraction
        for ext in extractors:
            ext_type = ext.get('type')
            ext_part = ext.get('part', 'body')
            
            if ext_type == 'regex':
                regexes = ext.get('regex') or []
                if ext_part == 'body' or ext_part == '':
                    for rx in regexes:
                        body_parts.append(generate_matching_string(rx))
            elif ext_type == 'kval':
                kvals = ext.get('kval') or []
                for kv in kvals:
                    # e.g., content_type or server header
                    headers[kv] = "Mock-Value"
            elif ext_type == 'json':
                # Generate a dummy json with extract key
                json_keys = ext.get('json') or ["key"]
                json_key = json_keys[0] if json_keys else "key"
                body_parts.append(f'{{"{json_key}": "mocked_extractor_value"}}')
                headers["Content-Type"] = "application/json"
                
        # Consolidate body
        body_text = "\n".join(body_parts) if body_parts else "Mock Mimic positive response"
        
        # Collect paths to register
        req_paths = []
        if raw_requests:
            for raw_req in raw_requests:
                # Parse raw request path & method
                first_line = raw_req.split('\n')[0].strip()
                match = re.match(r'^([A-Z]+)\s+(\S+)\s+HTTP', first_line)
                if match:
                    req_method = match.group(1)
                    req_path = clean_path(match.group(2))
                    req_paths.append((req_method, req_path))
        elif paths:
            for p in paths:
                req_paths.append((method, clean_path(p)))
                
        if not req_paths:
            req_paths.append(('GET', '/'))
            
        for req_method, req_path in req_paths:
            req_index += 1
            if not auto_mode:
                print(f"\n--- Configure Route {req_index} ---")
                print(f"Path: {req_method} {req_path}")
                print(f"Suggested Status: {status_code}")
                print(f"Suggested Headers: {headers}")
                print(f"Suggested Body contains: {body_parts}")
                
                # Interactive prompting
                user_status = input(f"Enter Status Code [{status_code}]: ").strip()
                if user_status:
                    try:
                        status_code = int(user_status)
                    except ValueError:
                        pass
                        
                user_body = input(f"Enter Response Body (leave empty to keep suggested): ").strip()
                if user_body:
                    body_text = user_body
                    
            routes.append({
                "method": req_method,
                "path": req_path,
                "status": status_code,
                "headers": headers,
                "body": body_text
            })
            
    # Save the configuration to mimicer/mimic_confs/<CVE-ID>/template.conf
    conf_dir = os.path.join(workspace_dir, "mimicer", "mimic_confs", template_id)
    os.makedirs(conf_dir, exist_ok=True)
    conf_path = os.path.join(conf_dir, "template.conf")
    
    conf_data = {
        "template_id": template_id,
        "template_path": yaml_path,
        "routes": routes
    }
    
    with open(conf_path, 'w', encoding='utf-8') as f:
        json.dump(conf_data, f, indent=4)
        
    print(f"\n[+] Successfully created mimic configuration in:")
    print(f"    {conf_path}")
    print(f"[+] Loaded {len(routes)} routes.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python mimicer.py <TEMPLATE-ID> | --all [--auto]")
        sys.exit(1)
        
    template_id = sys.argv[1]
    auto_mode = "--auto" in sys.argv
    
    workspace_dir = "../"
    csv_path = os.path.join(workspace_dir, "unverified.csv")
    
    if template_id == "--all":
        if not os.path.exists(csv_path):
            print(f"[-] CSV file not found: {csv_path}")
            sys.exit(1)
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 2:
                    continue
                tid = row[0].strip()
                
                conf_path = os.path.join(workspace_dir, "mimicer", "mimic_confs", tid, "template.conf")
                if os.path.exists(conf_path):
                    print(f"[*] Skipping {tid} (configuration already exists)")
                    continue
                    
                print(f"\n=====================================")
                print(f"Processing: {tid}")
                print(f"=====================================")
                process_template(tid, auto_mode, workspace_dir, csv_path)
    else:
        process_template(template_id, auto_mode, workspace_dir, csv_path)

if __name__ == "__main__":
    main()


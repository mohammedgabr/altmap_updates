# Mimicer & Mimic Server: Quick Start Guide

A local testing harness that converts unverified Nuclei HTTP templates into dynamic mock servers. The mock server responds with custom status codes, headers, and body payloads designed to satisfy all matchers and extractors defined in the template, ensuring a positive verification result when audited with Nuclei.

---

## 🚀 How It Works

1. **`mimicer.py`** (The Generator): Matches a template ID to its YAML file via `unverified.csv`, parses the template HTTP blocks, solves/satisfies all matchers and extractors, and writes a configuration rule map to `mimicer/mimic_confs/<ID>/template.conf`.
2. **`mimic_server.py`** (The HTTP Server): Loads the generated rule map and spins up a local server. It matches incoming HTTP methods, paths, and patterns to reply with the exact mock responses needed.

---

## 📦 Setup & Dependencies

The tools use standard python libraries and `PyYAML` to parse Nuclei templates.

Make sure your workspace environment has `pyyaml` installed:
```bash
pip3 install pyyaml
```

---

## 🛠️ Usage Guide

### 1. Generating a Mock Server Config (`mimicer.py`)

You can generate a mock configuration automatically or interactively.

#### Option A: Automatic Mode (Recommended)
This uses smart heuristics to satisfy word, regex, status code, and DSL matchers without asking for input:
```bash
python3 mimicer/mimicer.py CVE-2001-0537 --auto
```
*Outputs configuration file at:* `mimicer/mimic_confs/CVE-2001-0537/template.conf`

#### Option B: Interactive Mode
Walks you through every HTTP route parsed from the YAML block and lets you customize the status codes, headers, and response bodies:
```bash
python3 mimicer/mimicer.py CVE-2001-0537
```

#### Option C: Bulk Generation
You can generate configurations for all unverified templates in `unverified.csv` at once. It automatically skips templates that already have a configuration:
```bash
python3 mimicer/mimicer.py --all --auto
```

---

### 2. Booting the Mock Server (`mimic_server.py`)

Run the server by pointing to the generated config folder or directory:
```bash
# Starts the server on port 8080 (requires no sudo privileges)
python3 mimicer/mimic_server.py CVE-2001-0537 --port 8080 --host 127.0.0.1
```

Or by passing the exact filepath to `template.conf`:
```bash
python3 mimicer/mimic_server.py mimicer/mimic_confs/CVE-2001-0537/template.conf --port 8080
```

#### Automated Verification Mode
You can automatically test a template against the mock server to verify if it successfully triggers a match. The script will boot the server in the background, execute Nuclei, and copy the template file into `working_mimics` (on success) or `failed_mimics` (on failure) within the `mimicer` directory:
```bash
python3 mimicer/mimic_server.py CVE-2001-0537 --verify http://127.0.0.1:8080 --port 8080
```

---

### 3. Testing with Nuclei (End-to-End)

Once the mock server is running on port `8080`, test it with Nuclei directly against the localhost instance to confirm it registers a positive matching hit:

```bash
nuclei -t upstream/http/cves/2001/CVE-2001-0537.yaml -u http://127.0.0.1:8080
```

---

## 📝 Example Matcher Configurations

### Case A: Simple Matcher (`CVE-2001-0537`)
If the template expects status code `200` and the strings `"service config"`, `"Switch"`, and `"default-gateway"`, the generator auto-produces:
```json
{
    "template_id": "CVE-2001-0537",
    "routes": [
        {
            "method": "GET",
            "path": "/level/16/exec/show/config/CR",
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": "service config\nSwitch\ndefault-gateway"
        }
    ]
}
```

### Case B: Extractor Matcher (`CVE-2019-10232`)
If the template extracts database versions using regex `[0-9]{1,2}.[0-9]{1,2}.[0-9]{1,2}-MariaDB`, the generator automatically outputs:
```json
{
    "template_id": "CVE-2019-10232",
    "routes": [
        {
            "method": "GET",
            "path": "/glpi/scripts/unlock_tasks.php?cycle=1%20UNION%20ALL%20SELECT%201,(@@version)--%20&only_tasks=1",
            "status": 200,
            "headers": {"Content-Type": "text/html"},
            "body": "-MariaDB-\nStart unlock script\n10.10.10-MariaDB"
        }
    ]
}
```
This guarantees that Nuclei's extraction engine successfully matches and prints `10.10.10-MariaDB` upon execution.

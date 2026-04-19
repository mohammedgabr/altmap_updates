# AltMap Updates: System Guide & Workflow

This guide explains how the template indexing system works and how to manage templates as you test and verify them.

---

## 📂 Repository Structure

*   **/upstream**: A daily clone of the official Nuclei `http/` templates. **Do not edit these files.**
*   **/altmap_verified**: Your personal archive. Stores the "known-good" version of a template at the time you verified it.
*   **/altmap_verified/changed**: Your "Override" folder. Store templates here that you have **modified** to work specifically with AltMap.
*   **verified.csv**: Your master list of approved templates. Format: `template_id,relative/path/to/template.yaml`.
*   **unverified.csv**: Automatically generated daily with everything in `upstream/` that is not in your `verified.csv`.
*   **changed_after_verified.csv**: Alerts you when a template you verified has been updated in the official repo.

---

## ⚙️ How the Indexer (`main.go`) Works

The script scans the **`upstream/`** folder and builds the index following these rules for each template:

1.  **Verification Check**: It checks if the template's path is listed in your `verified.csv`.
2.  **Template Selection (Priority)**:
    *   **Priority 1 (Custom)**: If a file exists in `altmap_verified/changed/`, it uses **your edited version**.
    *   **Priority 2 (Official)**: Otherwise, it uses the official file from `upstream/`.
3.  **Naming**:
    *   If the template is **Verified**: It uses the name as defined in the file.
    *   If the template is **Unverified**: It adds a `[unverified]` prefix to the name.
4.  **Change Detection**:
    *   If a template is verified, it compares the `upstream/` version with your snapshot in `altmap_verified/`. If they differ, it adds the ID to `changed_after_verified.csv`.
5.  **Final Output**:
    *   Generates `cves.json` (JSONLines), `cves.json-checksum.txt`, and `tags-index.json`.

---

## 🛠️ Your Workflow

### 1. Identify a Template to Test
You can find new templates to test in the `unverified.csv` file or by browsing the `upstream/http/` directory.

### 2. If the Original Template works:
1.  **Add to List**: Add the template's ID and its path to `verified.csv`.
2.  **Archive Snapshot**: Copy the original `.yaml` file from `upstream/` into the `altmap_verified/` folder (at the same relative path).
    *   *Result*: In the next update, the `[unverified]` prefix will be removed from this template.

### 3. If the Template needs changes (Fixes/Optimization):
1.  **Add to List**: Add the ID and path to `verified.csv`.
2.  **Save your Fix**: Save your modified `.yaml` file into `altmap_verified/changed/` (at the same relative path).
    *   *Result*: The indexer will now ignore the official version and point the app to your custom version instead.

### 4. Handling Upstream Updates
If a template appears in `changed_after_verified.csv`:
1.  Check the difference between `upstream/` and your `altmap_verified/` snapshot.
2.  If you want to accept the new version: Copy it from `upstream/` to `altmap_verified/`.
3.  If you want to stick with your version: Do nothing.

---

## 🚀 Deployment
Every time you push changes to `verified.csv` or the `altmap_verified/` folder, the GitHub Action triggers, regenerates the index, and updates the checksum for your app.

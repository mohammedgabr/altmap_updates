<script>
  import { onMount } from 'svelte';

  let templates = [];
  let logs = [];
  let activeTemplateId = null;
  let status = "Inactive";
  let searchTerm = "";

  async function fetchTemplates() {
    try {
      const res = await fetch('/api/templates');
      templates = await res.json();
    } catch (e) {
      console.error("Failed to fetch templates", e);
    }
  }

  async function fetchLogs() {
    try {
      const res = await fetch('/api/logs');
      logs = await res.json();
    } catch (e) {
      console.error("Failed to fetch logs", e);
    }
  }

  async function activate(template) {
    try {
      const res = await fetch(`/api/activate?template_path=${encodeURIComponent(template.path)}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.status === "success") {
        activeTemplateId = template.id;
        status = "Active";
      }
    } catch (e) {
      alert("Activation failed: " + e.message);
    }
  }

  async function reset() {
    await fetch('/api/reset', { method: 'POST' });
    activeTemplateId = null;
    status = "Inactive";
    logs = [];
  }

  onMount(() => {
    fetchTemplates();
    const interval = setInterval(fetchLogs, 2000);
    return () => clearInterval(interval);
  });

  $: filteredTemplates = templates.filter(t => 
    t.id.toLowerCase().includes(searchTerm.toLowerCase()) || 
    t.name.toLowerCase().includes(searchTerm.toLowerCase())
  );
</script>

<div class="app-container">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="logo-section">
      <div class="logo-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00f2ff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
      </div>
      <h1 style="margin:0; font-size: 20px;" class="neon-text-cyan">Double Tester</h1>
    </div>

    <input 
      type="text" 
      placeholder="Search templates..." 
      class="search-input"
      bind:value={searchTerm}
    />

    <div class="template-list">
      {#each filteredTemplates as t}
        <div 
          class="template-item {activeTemplateId === t.id ? 'active' : ''}"
          on:click={() => activate(t)}
        >
          <div style="display:flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 11px; font-family: monospace; color: #00f2ff;">{t.id}</span>
            <span class="severity-{t.severity.toLowerCase()}">{t.severity}</span>
          </div>
          <div style="font-size: 13px; font-weight: 500;">{t.name}</div>
        </div>
      {/each}
    </div>
  </aside>

  <!-- Main Content -->
  <main class="main-content">
    <div class="top-cards">
      <div class="glass-card" style="text-align: center;">
        <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Mimic Status</div>
        <div class="status-badge {status === 'Active' ? 'active' : 'inactive'}">{status}</div>
        <div style="font-size: 11px; color: #484f58; font-family: monospace;">HOST: 127.0.0.1:5001</div>
      </div>

      <div class="glass-card" style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Active Template</div>
          <div class="neon-text-purple" style="font-size: 20px; margin-top: 4px;">{activeTemplateId || 'None Selected'}</div>
        </div>
        <div style="display: flex; gap: 12px;">
          <button on:click={reset}>Reset</button>
          <button class="primary" on:click={() => alert(`nuclei -u http://localhost:5001 -t ${templates.find(t => t.id === activeTemplateId)?.path || ''}`)}>Get Command</button>
        </div>
      </div>
    </div>

    <div class="log-container">
      <div class="log-header">
        <span style="font-weight: 600;">Real-Time Activity Log</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 8px; height: 8px; background: #3fb950; border-radius: 50%; box-shadow: 0 0 8px #3fb950;"></div>
          <span style="font-size: 11px; color: #8b949e;">LIVE FEED</span>
        </div>
      </div>
      <div class="log-feed">
        {#each [...logs].reverse() as log}
          <div class="log-entry">
            <span style="color: #484f58;">[{new Date().toLocaleTimeString()}]</span>
            <span style="color: {log.matched ? '#3fb950' : '#f85149'}; font-weight: bold;">{log.method}</span>
            <span class="neon-text-cyan">{log.path}</span>
            <span style="color: #8b949e;">→</span>
            <span style="color: #bc13fe;">{log.response}</span>
          </div>
        {:else}
          <div style="height: 100%; display: flex; align-items: center; justify-content: center; color: #484f58; font-style: italic;">
            Waiting for activity on port 5001...
          </div>
        {/each}
      </div>
    </div>
  </main>
</div>

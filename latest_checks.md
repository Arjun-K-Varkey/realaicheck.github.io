---
layout: page
title: Latest Checks
---

## Recent AI Misinfo Analyses
Community-powered archive (last 20 submissions). Share suspicious finds!

<div id="resultsList" style="max-width:800px;">
  <p>Loading latest...</p>
</div>

<script>
const API_URL = 'https://realaicheck-github-io.onrender.com/results?limit=20';

fetch(API_URL)
  .then(r => r.json())
  .then(results => {
    const container = document.getElementById('resultsList');
    if (results.length === 0) {
      container.innerHTML = '<p>No analyses yet—<a href="/submit">be first!</a></p>';
      return;
    }
    container.innerHTML = results.map(r => `
      <div style="border:1px solid #ddd; margin:10px 0; padding:20px; border-radius:8px;">
        <h4><a href="${r.url}" target="_blank">${r.url}</a></h4>
        <p><strong>Verdict:</strong> ${r.overall_verdict || 'Pending'} | 
           <strong>AI Prob:</strong> ${(r.ai_prob * 100).toFixed(1)}% | 
           <strong>Claims:</strong> ${r.claim_count}</p>
        <small>${new Date(r.timestamp).toLocaleString()}</small>
      </div>
    `).join('');
  })
  .catch(() => {
    document.getElementById('resultsList').innerHTML = '<p>Check back soon!</p>';
  });
</script>

<a href="/submit" style="display:inline-block; background:#0066cc; color:white; padding:12px 24px; text-decoration:none; border-radius:5px;">Submit New</a>

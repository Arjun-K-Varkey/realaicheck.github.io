---
layout: page
title: Submit a Claim
---

Have you spotted a suspicious deepfake video, AI-generated image, or viral misinformation on social media?

Submit it here—we prioritize high-engagement claims for quick verification.

Your tips help protect the truth in the AI era. All submissions are reviewed transparently.

### Quick Submission Form

<div id="formContainer" style="max-width:600px; margin:20px 0;">
  <div id="liveCheckForm">
    <label for="url"><strong>Link to the claim</strong> (X post, TikTok, Instagram, article, etc.) <span style="color:red;">*</span></label>
    <input type="url" name="url" id="url" placeholder="https://..." required style="width:100%; padding:12px; margin:10px 0; box-sizing:border-box; font-size:1em;">

    <label for="description"><strong>Description</strong> (what makes it suspicious?)</label>
    <textarea name="description" id="description" rows="6" placeholder="Briefly explain why this might be AI-generated or misleading..." style="width:100%; padding:12px; margin:10px 0; box-sizing:border-box; font-size:1em;"></textarea>

    <button id="submitBtn" onclick="analyzeUrl()" style="background:#0066cc; color:white; padding:14px 28px; border:none; font-size:1.1em; cursor:pointer; width:100%; margin:15px 0;">
      Analyze Claim
    </button>
  </div>

  <div id="loader" style="display:none; text-align:center; padding:20px;">
    <p><strong>Analyzing...</strong></p>
    <p><small>This may take 10-30 seconds as our models load. Thank you for your patience.</small></p>
  </div>

  <div id="results" style="display:none; margin-top:20px; padding:15px; border:1px solid #ccc; border-radius:5px; background:#f9f9f9;">
    <h3>Analysis Results</h3>
    <p><strong>URL:</strong> <span id="resultUrl"></span></p>
    <p><strong>Overall Verdict:</strong> <span id="verdictText" style="font-weight:bold; color:#d9534f;"></span></p>
    <p><strong>AI-Generated Probability:</strong> <span id="scoreText"></span></p>
    <div id="claimsSection" style="margin-top:15px;">
      <h4>Fact-Checked Claims:</h4>
      <ul id="claimsList"></ul>
    </div>
    <p><small>Full analysis saved. <a href="mailto:realaicheck.contact@gmail.com?subject=Analysis%20Report">Email us with questions.</a></small></p>
    <button onclick="resetForm()" style="background:#6c757d; color:white; padding:10px 20px; border:none; cursor:pointer; margin-top:10px;">Submit Another</button>
  </div>

  <div id="errorBox" style="display:none; margin-top:20px; padding:15px; border:1px solid #f5c6cb; border-radius:5px; background:#f8d7da; color:#721c24;">
    <strong>Error:</strong> <span id="errorText"></span>
  </div>
</div>

<p style="margin-top:30px;"><small><span style="color:red;">*</span> Required field. Submissions are anonymous.</small></p>

<p><strong>Alternative:</strong> Email tips directly to <a href="mailto:realaicheck.contact@gmail.com">realaicheck.contact@gmail.com</a> with the URL and your observations.</p>

<p>Thank you for helping combat AI misinformation!</p>

<script>
// Replace with your actual Render API endpoint
const API_URL = 'https://realaicheck-github-io.onrender.com/analyze';

function analyzeUrl() {
  const urlInput = document.getElementById('url').value.trim();
  const descInput = document.getElementById('description').value.trim();

  // Validate URL
  if (!urlInput) {
    showError('Please enter a URL to analyze.');
    return;
  }

  // Basic URL validation
  try {
    new URL(urlInput);
  } catch (e) {
    showError('Please enter a valid URL (e.g., https://example.com/article)');
    return;
  }

  // Hide previous results and show loader
  document.getElementById('results').style.display = 'none';
  document.getElementById('errorBox').style.display = 'none';
  document.getElementById('loader').style.display = 'block';
  document.getElementById('submitBtn').disabled = true;
  document.getElementById('submitBtn').style.opacity = '0.6';

  // Prepare request payload
  const payload = {
    url: urlInput,
    enable_playwright: false // Set to true if you want to enable browser fallback
  };

  // Send POST request to backend
  fetch(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  })
  .then(response => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
  })
  .then(data => {
    // Handle response from backend
    if (data.error) {
      showError(data.error);
    } else {
      displayResults(data);
    }
  })
  .catch(error => {
    console.error('Fetch error:', error);
    showError(`Network error: ${error.message}. Is the API running? Check your endpoint URL.`);
  })
  .finally(() => {
    document.getElementById('loader').style.display = 'none';
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('submitBtn').style.opacity = '1';
  });
}

function displayResults(data) {
  const resultsDiv = document.getElementById('results');
  const claimsList = document.getElementById('claimsList');

  // Populate verdict and score
  document.getElementById('resultUrl').textContent = data.url || 'Unknown';
  document.getElementById('verdictText').textContent = data.overall_verdict || 'Unable to determine';

  const aiScore = data.ai_detection?.probability_ai;
  if (aiScore !== undefined && aiScore !== null) {
    const percentage = (aiScore * 100).toFixed(1);
    document.getElementById('scoreText').innerHTML = `${percentage}% likely AI-generated (${data.ai_detection.verdict || 'Unknown'})`;
  } else {
    document.getElementById('scoreText').textContent = 'Not available';
  }

  // Populate claims
  claimsList.innerHTML = '';
  if (data.claims && data.claims.length > 0) {
    data.claims.forEach((claim, index) => {
      const li = document.createElement('li');
      li.innerHTML = `
        <strong>Claim ${index + 1}:</strong> ${claim.claim || 'N/A'}<br>
        <small><strong>Verdict:</strong> ${claim.verdict || 'Inconclusive'}</small><br>
        <small><strong>Supporting sources:</strong> ${(claim.supporting && claim.supporting.length) || 0}</small><br>
        <small><strong>Challenging sources:</strong> ${(claim.challenging && claim.challenging.length) || 0}</small>
      `;
      claimsList.appendChild(li);
    });
  } else {
    claimsList.innerHTML = '<li>No claims extracted from this content.</li>';
  }

  // Show results section
  resultsDiv.style.display = 'block';
  window.scrollTo({ top: resultsDiv.offsetTop - 50, behavior: 'smooth' });
}

function showError(message) {
  document.getElementById('errorBox').style.display = 'block';
  document.getElementById('errorText').textContent = message;
  document.getElementById('results').style.display = 'none';
}

function resetForm() {
  document.getElementById('url').value = '';
  document.getElementById('description').value = '';
  document.getElementById('results').style.display = 'none';
  document.getElementById('errorBox').style.display = 'none';
  document.getElementById('liveCheckForm').style.display = 'block';
  document.getElementById('submitBtn').disabled = false;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
</script>

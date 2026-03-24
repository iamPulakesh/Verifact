"use strict";

const API = {
  url: "/api/check/url",
  text: "/api/check/text",
  image: "/api/check/image",
};

const $ = id => document.getElementById(id);

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".panel");
const analyzeBtn = $("analyze-btn");
const progressWrap = $("progress-wrap");
const progressBar = $("progress-bar");
const progressLbl = $("progress-label");
const progressBW = $("progress-bar-wrap");
const results = $("results");
const errorCard = $("error-card");
const reportPanel = $("report-panel");
const errorMsg = $("error-msg");
const errorDismiss = $("error-dismiss");
const resetBtn = $("reset-btn");
const dropZone = $("drop-zone");
const dropIdle = $("drop-idle");
const dropPreview = $("drop-preview");
const previewImg = $("preview-img");
const previewMeta = $("preview-meta");
const removeBtn = $("remove-btn");
const imageInput = $("image-input");
const imageError = $("image-error");
const urlInput = $("url-input");
const urlError = $("url-error");
const textInput = $("text-input");
const textUrlError = $("text-url-error");
const textCounter = $("text-counter");

const themeToggle = $("theme-toggle");
const sunIcon = $("sun-icon");
const moonIcon = $("moon-icon");

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const isLight = theme === "light";
  sunIcon.style.display = isLight ? "none" : "block";
  moonIcon.style.display = isLight ? "block" : "none";
}

const savedTheme = localStorage.getItem("theme");
const systemPrefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
const initialTheme = savedTheme || (systemPrefersLight ? "light" : "dark");
applyTheme(initialTheme);

themeToggle.addEventListener("click", () => {
  const currentTheme = document.documentElement.getAttribute("data-theme");
  const newTheme = currentTheme === "light" ? "dark" : "light";
  localStorage.setItem("theme", newTheme);
  applyTheme(newTheme);
});

let activeTab = "url";
let imageFile = null;
let progressTimer = null;

tabs.forEach(tab => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  tab.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      switchTab(tab.dataset.tab);
    }
  });
});

function switchTab(name) {
  activeTab = name;
  tabs.forEach(t => {
    const on = t.dataset.tab === name;
    t.classList.toggle("active", on);
    t.setAttribute("aria-selected", on ? "true" : "false");
  });
  panels.forEach(p => {
    const on = p.id === `panel-${name}`;
    p.classList.toggle("active", on);
    p.hidden = !on;
  });
  updateAnalyzeBtn();
}

urlInput.addEventListener("input", updateAnalyzeBtn);
urlInput.addEventListener("keydown", e => {
  if (e.key === "Enter") tryAnalyze();
});

textInput.addEventListener("input", () => {
  const val = textInput.value.trim();
  const len = val.length;
  const max = parseInt(textInput.getAttribute("maxlength"), 10);
  textCounter.textContent = `${len} / ${max}`;
  textCounter.className = "char-counter" +
    (len > max * 0.9 ? " danger" : len > max * 0.75 ? " warn" : "");

  const isUrl = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$/.test(val);
  textUrlError.hidden = !isUrl;
  
  updateAnalyzeBtn();
});

function updateAnalyzeBtn() {
  let ready = false;
  if (activeTab === "url") {
    const val = urlInput.value.trim();
    const isValid = val.length > 0 && /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$/.test(val);
    urlError.hidden = val.length === 0 || isValid;
    ready = isValid;
  } else if (activeTab === "image") {
    ready = imageFile !== null;
  } else if (activeTab === "text") {
    const val = textInput.value.trim();
    const isUrl = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$/.test(val);
    ready = val.length >= 10 && !isUrl;
  }
  analyzeBtn.disabled = !ready;
}

imageInput.addEventListener("change", e => {
  if (e.target.files[0]) handleFile(e.target.files[0]);
});

dropZone.addEventListener("click", e => {
  if (!e.target.closest(".remove-btn")) imageInput.click();
});

dropZone.addEventListener("keydown", e => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); imageInput.click(); }
});

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));

dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});

removeBtn.addEventListener("click", e => {
  e.stopPropagation();
  clearImage();
});

function handleFile(file) {
  const allowed = ["image/jpeg", "image/png", "image/webp", "image/bmp"];
  imageError.hidden = true;

  if (!allowed.includes(file.type)) {
    imageError.textContent = "Unsupported file type. Please choose only JPG, PNG, WEBP, or BMP.";
    imageError.hidden = false;
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    imageError.textContent = "File too large. Maximum size is 5 MB.";
    imageError.hidden = false;
    return;
  }
  imageFile = file;
  const url = URL.createObjectURL(file);
  previewImg.src = url;
  previewMeta.textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  dropIdle.hidden = true;
  dropPreview.hidden = false;
  updateAnalyzeBtn();
}

function clearImage() {
  imageFile = null;
  imageInput.value = "";
  previewImg.src = "";
  imageError.hidden = true;
  dropIdle.hidden = false;
  dropPreview.hidden = true;
  updateAnalyzeBtn();
}

analyzeBtn.addEventListener("click", tryAnalyze);

function tryAnalyze() {
  if (analyzeBtn.disabled) return;
  analyze();
}

async function analyze() {
  hideError();
  hideResults();
  showProgress();
  setBtnLoading(true);
  startProgressAnimation();

  try {
    let response;
    if (activeTab === "url") {
      response = await fetchJSON(API.url, "POST", { url: urlInput.value.trim() });
    } else if (activeTab === "image") {
      const fd = new FormData();
      fd.append("file", imageFile);
      response = await fetchMultipart(API.image, fd);
    } else {
      response = await fetchJSON(API.text, "POST", { text: textInput.value.trim() });
    }

    finishProgress();
    await sleep(400);
    hideProgress();
    renderResults(response);
  } catch (err) {
    hideProgress();
    showError(err.message || "An unexpected error occurred. Please try again.");
  } finally {
    setBtnLoading(false);
    clearProgressTimer();
  }
}

async function fetchJSON(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(res);
}

async function fetchMultipart(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  return handleResponse(res);
}

async function handleResponse(res) {
  if (res.status === 429) {
    throw new Error("Rate limit exceeded. Please wait a moment and try again.");
  }
  if (!res.ok) {
    let detail = `Server error (${res.status})`;
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch (_) { }
    throw new Error(detail);
  }
  return res.json();
}

const STEPS = [
  { pct: 15, label: "Analyzing article...", delay: 800 },
  { pct: 45, label: "Gathering evidence...", delay: 2200 },
  { pct: 85, label: "Please wait while Verifact is generating the report...", delay: 3500 },
];

function startProgressAnimation() {
  setProgress(0, "Starting analysis...");
  let cumulativeDelay = 0;
  STEPS.forEach((step) => {
    cumulativeDelay += step.delay;
    const t = setTimeout(() => {
      setProgress(step.pct, step.label);
    }, cumulativeDelay);
    if (!progressTimer) progressTimer = [];
    progressTimer.push(t);
  });
}

function finishProgress() {
  setProgress(100, "Analysis complete!");
}

function clearProgressTimer() {
  if (progressTimer) {
    progressTimer.forEach(clearTimeout);
    progressTimer = null;
  }
}

function setProgress(pct, label) {
  progressBar.style.width = pct + "%";
  progressBW.setAttribute("aria-valuenow", pct);
  progressLbl.textContent = label;
}

function showProgress() {
  if (reportPanel) reportPanel.hidden = false;
  results.hidden = true;
  errorCard.hidden = true;
  progressWrap.hidden = false;
}

function hideProgress() {
  progressWrap.hidden = true;
}

function hideResults() {
  results.hidden = true;
}

function showError(msg) {
  if (reportPanel) reportPanel.hidden = false;
  progressWrap.hidden = true;
  results.hidden = true;
  errorMsg.textContent = msg;
  errorCard.hidden = false;
  errorCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideError() {
  errorCard.hidden = true;
}

function setBtnLoading(on) {
  analyzeBtn.disabled = on;
  analyzeBtn.classList.toggle("loading", on);
  const icon = analyzeBtn.querySelector(".btn-icon svg");
  if (on) {
    icon.innerHTML = `<circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="32" stroke="currentColor" stroke-width="2.5" fill="none"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle>`;
  } else {
    icon.innerHTML = `<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>`;
    updateAnalyzeBtn();
  }
}

resetBtn.addEventListener("click", reset);

function reset() {
  hideResults();
  hideError();
  if (reportPanel) reportPanel.hidden = true;
  document.querySelector(".input-card").scrollIntoView({ behavior: "smooth" });
}

errorDismiss.addEventListener("click", hideError);

function renderResults(data) {
  const verdictRaw = (data.verdict || "Unverified").toLowerCase();
  const confidence = Math.round((data.confidence_score || 0) * 100);

  const badge = $("verdict-badge");
  badge.className = `verdict-badge verdict-${verdictRaw}`;
  badge.textContent = (data.verdict || "UNVERIFIED").toUpperCase();

  $("conf-text").textContent = `Confidence: ${confidence}%`;
  const fill = $("conf-bar-fill");
  fill.className = `conf-bar-fill ${verdictRaw}`;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { fill.style.width = confidence + "%"; });
  });
  $("conf-bar-track").setAttribute("aria-valuenow", confidence);

  const titleEl = $("article-title");
  if (data.article_title) {
    titleEl.textContent = data.article_title;
    titleEl.hidden = false;
  } else {
    titleEl.hidden = true;
  }

  const reasonEl = $("reasoning");
  if (data.reasoning_summary) {
    reasonEl.textContent = data.reasoning_summary;
    reasonEl.hidden = false;
  } else {
    reasonEl.hidden = true;
  }

  const claimsBlock = $("claims-block");
  const claimsList = $("claims-list");
  const claims = data.claims_analyzed || [];

  if (claims.length) {
    claimsList.innerHTML = "";
    claims.forEach((c, i) => {
      claimsList.appendChild(buildClaimChip(c, i));
    });
    claimsBlock.hidden = false;
  } else {
    claimsBlock.hidden = true;
  }

  const sourcesBlock = $("sources-block");
  const sourcesList = $("sources-list");
  const sources = (data.sources_consulted || []).filter(Boolean).slice(0, 5);

  if (sources.length) {
    sourcesList.innerHTML = "";
    sources.forEach(src => {
      sourcesList.appendChild(buildSourceItem(src));
    });
    sourcesBlock.hidden = false;
  } else {
    sourcesBlock.hidden = true;
  }

  if (reportPanel) reportPanel.hidden = false;
  progressWrap.hidden = true;
  errorCard.hidden = true;
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildClaimChip(c, index) {
  const status = (c.status || "Unverifiable").toLowerCase();
  const confidence = (c.confidence || "Low").toLowerCase();
  const statusClass = status.includes("support") ? "supported"
    : status.includes("contradict") ? "contradicted"
      : "unverifiable";

  const statusDisplay = status.includes("support") ? "Supported"
    : status.includes("contradict") ? "Contradicted"
      : "Unverifiable";

  const confClass = confidence === "high" ? "badge-conf-high"
    : confidence === "medium" ? "badge-conf-medium"
      : "badge-conf-low";

  const confDisplay = (c.confidence || "Low");

  const div = document.createElement("div");
  div.className = `claim-chip ${statusClass}`;
  div.style.animationDelay = `${index * 60}ms`;
  div.innerHTML = `
    <div class="claim-header">
      <span class="claim-text">${esc(c.claim || "Unknown claim")}</span>
      <div class="claim-badges">
        <span class="badge badge-status-${statusClass}">${statusDisplay}</span>
        <span class="badge ${confClass}">${esc(confDisplay)}</span>
      </div>
    </div>
    <div class="claim-evidence">${esc(c.evidence || "No evidence provided")}</div>
  `;
  return div;
}

function buildSourceItem(src) {
  src = src.trim();
  const isUrl = src.startsWith("http://") || src.startsWith("https://");
  const display = src.length > 70 ? src.slice(0, 67) + "…" : src;

  const el = document.createElement(isUrl ? "a" : "span");
  el.className = "source-item";
  if (isUrl) {
    el.href = src;
    el.target = "_blank";
    el.rel = "noopener noreferrer";
    el.setAttribute("aria-label", `Source: ${src}`);
    el.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      ${esc(display)}
    `;
  } else {
    el.textContent = display;
  }
  return el;
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

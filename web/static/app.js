const ACCEPTED_EXTENSIONS = new Set([
  ".pdf",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".gif",
  ".bmp",
  ".tiff",
  ".tif",
]);

const PROCESS_TIMEOUT_MS = 60_000;
const TIMEOUT_MESSAGE =
  "Request timed out after 1 minute. Please check your network connection and try again.";
const NETWORK_ERROR_MESSAGE =
  "Unable to reach the server. Please check your network connection and try again.";

const form = document.getElementById("upload-form");
const dropzone = document.getElementById("dropzone");
const filesInput = document.getElementById("files");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultsPanel = document.getElementById("results-panel");
const resultsBody = document.getElementById("results-body");
const downloadLink = document.getElementById("download-link");
const excelDownloadLink = document.getElementById("excel-download-link");
const errorsEl = document.getElementById("errors");
const fileListPanel = document.getElementById("file-list-panel");
const fileList = document.getElementById("file-list");
const clearFilesBtn = document.getElementById("clear-files-btn");
const overlay = document.getElementById("overlay");
const loadingDialog = document.getElementById("loading-dialog");
const loadingMessageEl = document.getElementById("loading-message");
const errorDialog = document.getElementById("error-dialog");
const errorMessageEl = document.getElementById("error-message");
const dismissErrorBtn = document.getElementById("dismiss-error-btn");

/** @type {File[]} */
let selectedFiles = [];

dropzone.addEventListener("click", () => filesInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    filesInput.click();
  }
});

filesInput.addEventListener("change", () => {
  addFiles(Array.from(filesInput.files || []));
  filesInput.value = "";
});

["dragenter", "dragover"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    event.stopPropagation();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (event) => {
  const droppedFiles = Array.from(event.dataTransfer?.files || []);
  addFiles(droppedFiles);
});

clearFilesBtn.addEventListener("click", () => {
  selectedFiles = [];
  syncInputFiles();
  renderFileList();
  setStatus("", "");
});

dismissErrorBtn.addEventListener("click", hideOverlay);

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (selectedFiles.length === 0) {
    showError("Choose at least one receipt.");
    setStatus("Choose at least one receipt.", "error");
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files", file));

  submitBtn.disabled = true;
  showLoading(`Processing ${selectedFiles.length} receipt(s)...`);
  setStatus("", "");

  try {
    const response = await fetchWithTimeout(
      "/api/process",
      {
        method: "POST",
        body: formData,
      },
      PROCESS_TIMEOUT_MS,
    );

    const payload = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(formatApiError(payload));
    }

    hideOverlay();
    renderResults(payload);
    setStatus(`Processed ${payload.rows.length} receipt(s).`, "success");
  } catch (error) {
    const message = error.message || "Unexpected error.";
    showError(message);
    setStatus(message, "error");
  } finally {
    submitBtn.disabled = selectedFiles.length === 0;
  }
});

function addFiles(files) {
  const accepted = [];
  const rejected = [];

  files.forEach((file) => {
    if (isSupportedFile(file)) {
      accepted.push(file);
    } else {
      rejected.push(file.name);
    }
  });

  selectedFiles = dedupeFiles([...selectedFiles, ...accepted]);
  syncInputFiles();
  renderFileList();

  if (rejected.length > 0) {
    setStatus(`Skipped unsupported file(s): ${rejected.join(", ")}`, "error");
  } else if (accepted.length > 0) {
    setStatus(`${selectedFiles.length} file(s) ready to process.`, "success");
  }
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  syncInputFiles();
  renderFileList();
  setStatus(selectedFiles.length ? `${selectedFiles.length} file(s) ready to process.` : "", "");
}

function syncInputFiles() {
  const dataTransfer = new DataTransfer();
  selectedFiles.forEach((file) => dataTransfer.items.add(file));
  filesInput.files = dataTransfer.files;
  submitBtn.disabled = selectedFiles.length === 0;
}

function renderFileList() {
  fileList.innerHTML = "";

  if (selectedFiles.length === 0) {
    fileListPanel.classList.add("hidden");
    return;
  }

  fileListPanel.classList.remove("hidden");

  selectedFiles.forEach((file, index) => {
    const item = document.createElement("li");
    item.className = "file-item";

    const meta = document.createElement("div");
    meta.className = "file-meta";
    meta.innerHTML = `
      <span class="file-name">${escapeHtml(file.name)}</span>
      <span class="file-size">${escapeHtml(formatFileSize(file.size))}</span>
    `;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "text-button";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeFile(index));

    item.append(meta, removeBtn);
    fileList.appendChild(item);
  });
}

function isSupportedFile(file) {
  const extension = getExtension(file.name);
  return ACCEPTED_EXTENSIONS.has(extension);
}

function getExtension(filename) {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex === -1 ? "" : filename.slice(dotIndex).toLowerCase();
}

function dedupeFiles(files) {
  const seen = new Set();
  return files.filter((file) => {
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatFileSize(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderResults(payload) {
  resultsBody.innerHTML = "";
  payload.rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.payment_date)}</td>
      <td>${escapeHtml(row.category)}</td>
      <td>${escapeHtml(row.amount)}</td>
      <td>${escapeHtml(row.currency)}</td>
      <td>${escapeHtml(row.reference_file)}</td>
    `;
    resultsBody.appendChild(tr);
  });

  downloadLink.href = payload.download_url;
  downloadLink.download = payload.csv_filename;
  excelDownloadLink.href = payload.excel_download_url;
  excelDownloadLink.download = payload.xlsx_filename;

  if (payload.errors.length > 0) {
    errorsEl.textContent = payload.errors
      .map((item) => `${item.file}: ${item.error}`)
      .join("\n");
  } else {
    errorsEl.textContent = "";
  }

  resultsPanel.classList.remove("hidden");
}

function setStatus(message, tone) {
  statusEl.textContent = message;
  statusEl.className = `status ${tone || ""}`.trim();
}

function showLoading(message) {
  loadingMessageEl.textContent = message;
  errorDialog.classList.add("hidden");
  loadingDialog.classList.remove("hidden");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("overlay-open");
}

function showError(message) {
  errorMessageEl.textContent = message;
  loadingDialog.classList.add("hidden");
  errorDialog.classList.remove("hidden");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("overlay-open");
}

function hideOverlay() {
  overlay.classList.add("hidden");
  loadingDialog.classList.add("hidden");
  errorDialog.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("overlay-open");
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error(TIMEOUT_MESSAGE);
    }
    throw new Error(NETWORK_ERROR_MESSAGE);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function formatApiError(payload) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join("\n");
  }
  return "Processing failed.";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const form = document.getElementById("upload-form");
const filesInput = document.getElementById("files");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("status");
const resultsPanel = document.getElementById("results-panel");
const resultsBody = document.getElementById("results-body");
const downloadLink = document.getElementById("download-link");
const errorsEl = document.getElementById("errors");

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const files = filesInput.files;
  if (!files || files.length === 0) {
    setStatus("Choose at least one receipt.", "error");
    return;
  }

  const formData = new FormData();
  Array.from(files).forEach((file) => formData.append("files", file));

  submitBtn.disabled = true;
  setStatus("Processing receipts with OCR and Hermes Agent...", "");

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Processing failed.");
    }

    renderResults(payload);
    setStatus(`Processed ${payload.rows.length} receipt(s).`, "success");
  } catch (error) {
    setStatus(error.message || "Unexpected error.", "error");
  } finally {
    submitBtn.disabled = false;
  }
});

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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const $ = (selector) => document.querySelector(selector);
const opacitySlider = $("#opacity");
const opacityValue = $("#opacity-value");

if (opacitySlider && opacityValue) {
  opacitySlider.addEventListener("input", () => {
    opacityValue.value = opacitySlider.value;
    opacityValue.textContent = opacitySlider.value;
  });
}

for (const [sliderId, outputId] of [
  ["#top-opacity", "#top-opacity-value"],
  ["#bottom-opacity", "#bottom-opacity-value"],
]) {
  const slider = $(sliderId);
  const output = $(outputId);
  slider.addEventListener("input", () => {
    output.value = slider.value;
    output.textContent = slider.value;
    updateBannerPreview();
  });
}

const errorAlert = $("[data-alert-message]");
if (errorAlert) {
  window.alert(errorAlert.textContent.trim());
}

const collageForm = $("#collage-form");
const collageInput = $("#collage-files");
const replacementInput = $("#replace-file");
const preview = $("#collage-preview");
const collageMessage = $("#collage-message");
const collageCount = $("#collage-count");
let collageFiles = [];
let replaceIndex = -1;
let previewUrls = [];
let bannerLogoUrl = null;

function layoutBoxes(count) {
  if (count === 1) return [[0, 0, 100, 100]];
  if (count === 2) return [[0, 0, 50, 100], [50, 0, 50, 100]];
  if (count === 3) return [[0, 0, 50, 50], [50, 0, 50, 50], [0, 50, 100, 50]];
  if (count === 4) {
    return [[0, 0, 50, 50], [50, 0, 50, 50], [0, 50, 50, 50], [50, 50, 50, 50]];
  }
  return [];
}

function replaceFileList() {
  const transfer = new DataTransfer();
  collageFiles.forEach((file) => transfer.items.add(file));
  collageInput.files = transfer.files;
}

function updateBannerPreview() {
  const top = $("#banner-top-preview");
  const bottom = $("#banner-bottom-preview");
  if (!top || !bottom) return;
  const withOpacity = (hex, opacity) => {
    const channels = hex.match(/[0-9a-f]{2}/gi).map((value) => parseInt(value, 16));
    return `rgba(${channels.join(",")},${Number(opacity) / 255})`;
  };
  top.style.backgroundColor = withOpacity($("#top-color").value, $("#top-opacity").value);
  bottom.style.backgroundColor = withOpacity(
    $("#bottom-color").value,
    $("#bottom-opacity").value,
  );
  $("#banner-title-preview").textContent = $("#banner-title").value || "";
  $("#banner-description-preview").textContent = $("#banner-description").value || "";
  updatePreviewLogo();
}

function updatePreviewLogo() {
  const previewLogo = $("#banner-logo-preview");
  const logoFile = $("#brand-logo").files[0];
  if (!previewLogo) return;
  if (bannerLogoUrl) {
    URL.revokeObjectURL(bannerLogoUrl);
    bannerLogoUrl = null;
  }
  if (!logoFile) {
    previewLogo.removeAttribute("src");
    previewLogo.hidden = true;
    return;
  }
  bannerLogoUrl = URL.createObjectURL(logoFile);
  previewUrls.push(bannerLogoUrl);
  previewLogo.src = bannerLogoUrl;
  previewLogo.hidden = false;
}

function renderPreview() {
  previewUrls.forEach((url) => URL.revokeObjectURL(url));
  previewUrls = [];
  bannerLogoUrl = null;
  preview.replaceChildren();
  collageCount.textContent = `${collageFiles.length} / 4 files`;
  const canvas = $("#canvas-preset").value;
  preview.style.aspectRatio = canvas === "square" ? "1 / 1" : "16 / 9";
  const [canvasWidth, canvasHeight] = canvas === "square" ? [1080, 1080] : [1280, 720];
  const bannerHeight = canvasHeight / 8;
  const bannerPadding = Math.max(8, canvasWidth / 100);
  preview.style.setProperty(
    "--banner-text-x",
    `${((bannerHeight + bannerPadding) / canvasWidth) * 100}%`,
  );
  preview.style.setProperty("--banner-slot-width", `${(bannerHeight / canvasWidth) * 100}%`);

  if (collageFiles.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-preview";
    empty.textContent = "Select media to preview the automatic layout.";
    preview.append(empty);
    collageMessage.textContent = "";
    updateBannerPreview();
    return;
  }

  const boxes = layoutBoxes(collageFiles.length);
  collageFiles.forEach((file, index) => {
    const [x, y, width, height] = boxes[index];
    const cell = document.createElement("div");
    cell.className = "preview-cell";
    Object.assign(cell.style, {
      left: `${x}%`,
      top: `${y}%`,
      width: `${width}%`,
      height: `${height}%`,
    });

    const url = URL.createObjectURL(file);
    previewUrls.push(url);
    const media = document.createElement(file.type.startsWith("video/") ? "video" : "img");
    media.className = "preview-media";
    media.src = url;
    if (media instanceof HTMLVideoElement) {
      media.muted = true;
      media.loop = true;
      media.autoplay = true;
      media.playsInline = true;
    } else {
      media.alt = file.name;
    }
    cell.append(media);

    const label = document.createElement("span");
    label.className = "preview-label";
    label.textContent = `${index + 1}. ${file.name}`;
    cell.append(label);

    const actions = document.createElement("div");
    actions.className = "preview-actions";
    const replaceButton = document.createElement("button");
    replaceButton.type = "button";
    replaceButton.textContent = "Replace";
    replaceButton.addEventListener("click", () => {
      replaceIndex = index;
      replacementInput.value = "";
      replacementInput.click();
    });
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.textContent = "Remove";
    removeButton.setAttribute("aria-label", `Remove ${file.name}`);
    removeButton.addEventListener("click", () => {
      collageFiles.splice(index, 1);
      replaceFileList();
      renderPreview();
    });
    actions.append(replaceButton, removeButton);
    cell.append(actions);
    preview.append(cell);
  });

  const banner = document.createElement("div");
  banner.className = "preview-banner";
  banner.innerHTML = `
    <div id="banner-top-preview" class="preview-band preview-band-top">
      <img id="banner-logo-preview" alt="" hidden>
      <span id="banner-title-preview"></span>
    </div>
    <div id="banner-bottom-preview" class="preview-band preview-band-bottom">
      <span id="banner-description-preview"></span>
    </div>`;
  preview.append(banner);
  updateBannerPreview();
  collageMessage.textContent = "";
}

collageInput.addEventListener("change", () => {
  const addedFiles = Array.from(collageInput.files || []);
  if (collageFiles.length + addedFiles.length > 4) {
    collageMessage.textContent = "Choose no more than four files. Remove an item to make room.";
    replaceFileList();
    return;
  }
  collageFiles.push(...addedFiles);
  replaceFileList();
  renderPreview();
});

replacementInput.addEventListener("change", () => {
  const replacement = replacementInput.files && replacementInput.files[0];
  if (replacement && replaceIndex >= 0) {
    collageFiles[replaceIndex] = replacement;
    replaceFileList();
    renderPreview();
  }
  replaceIndex = -1;
});

$("#canvas-preset").addEventListener("change", renderPreview);
$("#brand-logo").addEventListener("change", updateBannerPreview);
for (const selector of ["#top-color", "#bottom-color", "#banner-title", "#banner-description"]) {
  $(selector).addEventListener("input", updateBannerPreview);
}
document.querySelectorAll(".swatches").forEach((group) => {
  group.addEventListener("click", (event) => {
    const swatch = event.target.closest("[data-color]");
    if (!swatch) return;
    $(`#${group.dataset.colorTarget}`).value = swatch.dataset.color;
    updateBannerPreview();
  });
});

collageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (collageFiles.length < 1 || collageFiles.length > 4) {
    collageMessage.textContent = "Upload between one and four files before rendering.";
    return;
  }

  const formData = new FormData(collageForm);
  formData.delete("media");
  collageFiles.forEach((file) => formData.append("media", file, file.name));
  const submitButton = $("#collage-submit");
  submitButton.disabled = true;
  submitButton.textContent = "Rendering…";
  collageMessage.textContent = "Preparing your collage. Video rendering can take a little while.";
  try {
    const response = await fetch("/collage", { method: "POST", body: formData });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Could not render the collage.");
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    const downloadUrl = link.href;
    link.download = blob.type === "video/mp4" ? "watermark-collage.mp4" : "watermark-collage.jpg";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    collageMessage.textContent = "Your collage is ready and downloaded.";
  } catch (error) {
    collageMessage.textContent = error.message || "Could not render the collage.";
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Render collage & download";
  }
});

const socialForm = $("#social-inspect-form");
const socialMessage = $("#social-message");
const socialOptions = $("#social-options");
const socialFormat = $("#social-format");
const socialDownload = $("#social-download");

socialForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  socialOptions.hidden = true;
  socialMessage.textContent = "Checking the public media link…";
  try {
    const response = await fetch("/social/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("#social-url").value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not inspect this link.");
    $("#social-title-preview").textContent = payload.title;
    socialFormat.replaceChildren();
    payload.formats.forEach((format) => {
      const option = document.createElement("option");
      option.value = format.format_id;
      option.textContent = format.label;
      socialFormat.append(option);
    });
    socialOptions.hidden = false;
    socialMessage.textContent = "Choose a quality to download.";
  } catch (error) {
    socialMessage.textContent = error.message || "Could not inspect this link.";
  }
});

socialDownload.addEventListener("click", async () => {
  socialDownload.disabled = true;
  socialDownload.textContent = "Downloading…";
  socialMessage.textContent = "Fetching media into temporary storage…";
  try {
    const response = await fetch("/social/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: $("#social-url").value,
        format_id: socialFormat.value,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Download failed.");
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    const downloadUrl = link.href;
    const contentDisposition = response.headers.get("Content-Disposition") || "";
    const suggestedName = contentDisposition.match(/filename="([^"]+)"/);
    link.download = suggestedName
      ? suggestedName[1]
      : `social-media.${blob.type.split("/")[1] || "mp4"}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    socialMessage.textContent = "Download started.";
  } catch (error) {
    socialMessage.textContent = error.message || "Download failed.";
  } finally {
    socialDownload.disabled = false;
    socialDownload.textContent = "Download to device";
  }
});

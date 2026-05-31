import { createVrmViewer } from "./vrm-viewer.js";

const state = {
  dataSources: {},
  datasets: [],
  samples: [],
  selected: null,
  raw: null,
  processed: null,
  frame: 0,
  playing: false,
  playbackTimer: null,
  playbackStartMs: 0,
  playbackStartFrame: 0,
  showHands: false,
  showTrails: true,
  viewYaw: 0,
  viewPitch: 0.08,
  viewZoom: 1,
  viewDragging: false,
  viewPointer: [0, 0],
};

const $ = (id) => document.getElementById(id);
const FINGER_PATTERNS = ["thumb", "index", "middle", "ring", "little"];
const ROOT_NAMES = ["hips", "pelvis", "root"];
const CURRENT_TRAIL = 48;
const THEME_KEY = "virea-theme";

let vrmViewer = null;

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

function formatErrorTable(quality) {
  if (!quality) return "";
  const lines = [];
  lines.push(`Status: ${quality.status || "unknown"} | Frames: ${quality.frame_count} | Joints: ${quality.joint_count}`);
  lines.push(`BBox: [${(quality.bbox_min || []).map((v) => v.toFixed(3)).join(", ")}] → [${(quality.bbox_max || []).map((v) => v.toFixed(3)).join(", ")}]`);

  if (quality.ground_contact) {
    const gc = quality.ground_contact;
    lines.push(`\nGround Contact:`);
    lines.push(`  Floating: ${gc.floating_frames}/${gc.total_frames} (${(gc.floating_ratio * 100).toFixed(1)}%)`);
    lines.push(`  Penetrating: ${gc.penetrating_frames}/${gc.total_frames} (${(gc.penetrating_ratio * 100).toFixed(1)}%)`);
    lines.push(`  Foot height range: [${gc.min_foot_height_m?.toFixed(4)}m, ${gc.max_foot_height_m?.toFixed(4)}m]`);
  }

  if (quality.velocity) {
    const v = quality.velocity;
    lines.push(`\nVelocity:`);
    lines.push(`  Mean: ${v.mean_speed_m_s?.toFixed(3)} m/s | Max: ${v.max_speed_m_s?.toFixed(3)} m/s`);
    lines.push(`  Jittery joints: ${v.jittery_joints} (threshold: ${v.jitter_threshold_m_s} m/s)`);
  }

  if (quality.retarget_error) {
    const re = quality.retarget_error;
    if (re.status === "shape_mismatch") {
      lines.push(`\nRetarget Error: shape mismatch ${JSON.stringify(re.source_shape)} vs ${JSON.stringify(re.target_shape)}`);
    } else {
      lines.push(`\nRetarget Error (source → target):`);
      lines.push(`  Overall: mean=${re.overall_mean_m?.toFixed(5)}m  max=${re.overall_max_m?.toFixed(5)}m  std=${re.overall_std_m?.toFixed(5)}m`);
      lines.push(`  Worst: frame=${re.worst_frame}  joint="${re.worst_joint_name}"`);
    }
  }

  if (quality.per_joint_errors && quality.per_joint_errors.length > 0) {
    lines.push(`\nPer-Joint Errors (sorted by max):`);
    lines.push(`  ${"Joint".padEnd(22)} ${"Mean(m)".padStart(9)} ${"Max(m)".padStart(9)} ${"Std(m)".padStart(9)} ${"Frame".padStart(6)}`);
    lines.push(`  ${"─".repeat(58)}`);
    const top = quality.per_joint_errors.slice(0, 15);
    for (const je of top) {
      lines.push(
        `  ${je.joint.padEnd(22)} ${je.mean_error_m.toFixed(5).padStart(9)} ${je.max_error_m.toFixed(5).padStart(9)} ${je.std_error_m.toFixed(5).padStart(9)} ${String(je.worst_frame).padStart(6)}`,
      );
    }
    if (quality.per_joint_errors.length > 15) {
      lines.push(`  ... ${quality.per_joint_errors.length - 15} more joints`);
    }
  }

  if (quality.symmetry && quality.symmetry.details?.length > 0) {
    lines.push(`\nSymmetry (max asymmetry: ${(quality.symmetry.max_asymmetry * 100).toFixed(1)}%):`);
    for (const s of quality.symmetry.details) {
      lines.push(`  ${s.pair}: ${(s.asymmetry_ratio * 100).toFixed(1)}%`);
    }
  }

  return lines.join("\n");
}

function metaSummary(payload) {
  if (!payload) return "";
  const q = payload.quality;
  if (q && (q.per_joint_errors || q.retarget_error || q.ground_contact)) {
    return formatErrorTable(q);
  }
  return JSON.stringify(
    {
      fps: payload.fps,
      frames: payload.frame_count,
      joints: payload.skeleton?.joint_names?.length,
      quality: q,
    },
    null,
    2,
  );
}

function applyTheme(theme) {
  const resolved = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = resolved;
  localStorage.setItem(THEME_KEY, resolved);
  $("themeToggle").textContent = resolved === "dark" ? "Light Theme" : "Dark Theme";
  vrmViewer?.setTheme?.(resolved);
}

function cssVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function isDarkTheme() {
  return document.documentElement.dataset.theme === "dark";
}

function sampleText(sample) {
  return sample?.text || sample?.metadata?.object_name || sample?.metadata?.name || "";
}

function hasFingerName(name) {
  const lower = String(name || "").toLowerCase();
  return FINGER_PATTERNS.some((pattern) => lower.includes(pattern));
}

function rootIndex(payload) {
  const names = payload?.skeleton?.joint_names || [];
  for (const name of ROOT_NAMES) {
    const index = names.findIndex((item) => String(item).toLowerCase() === name);
    if (index >= 0) return index;
  }
  return 0;
}

function visibleJointIndices(payload, showHands) {
  const names = payload?.skeleton?.joint_names || [];
  return names
    .map((name, index) => ({ name, index }))
    .filter(({ name, index }) => index >= 0 && (showHands || !hasFingerName(name)))
    .map(({ index }) => index);
}

function isFinitePoint(point) {
  return (
    Array.isArray(point) &&
    point.length >= 3 &&
    Number.isFinite(point[0]) &&
    Number.isFinite(point[1]) &&
    Number.isFinite(point[2])
  );
}

function normalizeFrames(payload, anchorFrameIndex = null) {
  const frames = payload?.frames?.positions || [];
  if (!frames.length) return [];
  const anchorIndex = rootIndex(payload);
  const frameIndex = Math.min(
    Math.max(anchorFrameIndex ?? state.frame, 0),
    Math.max(frames.length - 1, 0),
  );
  const anchor = frames[frameIndex]?.[anchorIndex] || frames[0]?.[anchorIndex] || [0, 0, 0];
  return frames.map((frame) =>
    frame.map((point) => [point[0] - anchor[0], point[1] - anchor[1], point[2] - anchor[2]]),
  );
}

function rotatePoint(point) {
  const yaw = state.viewYaw;
  const pitch = state.viewPitch;
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  const x = point[0] * cy - point[2] * sy;
  const z = point[0] * sy + point[2] * cy;
  const y = point[1] * cp - z * sp;
  const rz = point[1] * sp + z * cp;
  return [x, y, rz];
}

function boundsFor(payloads, canvas) {
  const points = [];
  for (const payload of payloads) {
    const frames = payload?.frames?.positions || [];
    if (!frames.length) continue;
    const visible = new Set(visibleJointIndices(payload, state.showHands));
    const root = rootIndex(payload);
    const stride = Math.max(1, Math.floor(frames.length / 96));
    for (let frameIndex = 0; frameIndex < frames.length; frameIndex += stride) {
      const frame = frames[frameIndex];
      const anchor = frame?.[root] || [0, 0, 0];
      for (const index of visible) {
        if (!isFinitePoint(frame?.[index])) continue;
        const point = frame[index];
        points.push(rotatePoint([point[0] - anchor[0], point[1] - anchor[1], point[2] - anchor[2]]));
      }
    }
  }
  if (!points.length) return { cx: 0, cy: 0.8, scale: 180, zoom: state.viewZoom };
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = Math.max(maxX - minX, 0.6);
  const height = Math.max(maxY - minY, 1.2);
  const usableWidth = Math.max(canvas.width * 0.70, 1);
  const usableHeight = Math.max(canvas.height * 0.76, 1);
  return {
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    scale: Math.min(usableWidth / width, usableHeight / height) * state.viewZoom,
  };
}

function projectPoint(point, bounds, canvas) {
  const rotated = rotatePoint(point);
  const x = canvas.width / 2 + (rotated[0] - bounds.cx) * bounds.scale;
  const y = canvas.height * 0.56 - (rotated[1] - bounds.cy) * bounds.scale;
  return [x, y, rotated[2] || 0];
}

function drawBackground(ctx, width, height) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = cssVar("--canvas", "#fff8ec");
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = cssVar("--grid", "rgba(20, 59, 76, 0.12)");
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 32) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y < height; y += 32) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function drawSkeletonFrame(ctx, canvas, payload, frames, frame, bounds, alpha = 1, showHands = false) {
  const jointNames = payload?.skeleton?.joint_names || [];
  const visible = new Set(visibleJointIndices(payload, showHands));
  const edges = (payload?.skeleton?.edges || []).filter(([a, b]) => visible.has(a) && visible.has(b));
  const skeletonRgb = isDarkTheme() ? "190, 218, 220" : "20, 59, 76";
  const rootRgb = isDarkTheme() ? "226, 118, 66" : "200, 95, 47";

  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const [a, b] of edges) {
    if (!isFinitePoint(frame[a]) || !isFinitePoint(frame[b])) continue;
    const pa = projectPoint(frame[a], bounds, canvas);
    const pb = projectPoint(frame[b], bounds, canvas);
    const depth = Math.max(-1, Math.min(1, (pa[2] + pb[2]) / 2));
    ctx.strokeStyle = `rgba(${skeletonRgb}, ${Math.max(0.03, Math.min(0.9, alpha * (0.38 + depth * 0.10)))})`;
    ctx.lineWidth = alpha < 1 ? 2.4 : 4;
    ctx.beginPath();
    ctx.moveTo(pa[0], pa[1]);
    ctx.lineTo(pb[0], pb[1]);
    ctx.stroke();
  }

  frame.forEach((point, index) => {
    if (!visible.has(index)) return;
    if (!isFinitePoint(point)) return;
    const [x, y] = projectPoint(point, bounds, canvas);
    const isRoot = index === rootIndex(payload);
    ctx.fillStyle = isRoot ? `rgba(${rootRgb}, ${alpha})` : `rgba(${skeletonRgb}, ${alpha})`;
    ctx.beginPath();
    ctx.arc(x, y, isRoot ? 5.5 : 3.0, 0, Math.PI * 2);
    ctx.fill();
  });

  if (jointNames.length && state.showTrails) {
    const root = rootIndex(payload);
    const trail = [];
    const trailEnd = Math.min(state.frame, frames.length - 1);
    for (let i = Math.max(0, trailEnd - CURRENT_TRAIL); i <= trailEnd; i += 1) {
      if (isFinitePoint(frames[i]?.[root])) trail.push(projectPoint(frames[i][root], bounds, canvas));
    }
    if (trail.length > 1) {
      ctx.save();
      ctx.setLineDash([8, 8]);
      ctx.strokeStyle = isDarkTheme() ? "rgba(226, 118, 66, 0.48)" : "rgba(200, 95, 47, 0.35)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(trail[0][0], trail[0][1]);
      for (const point of trail.slice(1)) {
        ctx.lineTo(point[0], point[1]);
      }
      ctx.stroke();
      ctx.restore();
    }
  }
}

function drawSkeleton(canvas, payload, sharedBounds) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  drawBackground(ctx, width, height);

  if (!payload?.frames?.positions?.length) return;
  const frames = normalizeFrames(payload);
  const frameIndex = Math.min(state.frame, frames.length - 1);
  drawSkeletonFrame(ctx, canvas, payload, frames, frames[frameIndex], sharedBounds, 1, state.showHands);
}

function renderPreview() {
  const maxFrames = Math.max(state.raw?.frame_count || 0, state.processed?.frame_count || 0);
  const maxFrame = Math.max(maxFrames - 1, 0);
  const frameValue = Math.min(Math.floor(state.frame), maxFrame);
  $("frameSlider").max = maxFrame;
  $("frameSlider").value = frameValue;
  $("frameLabel").textContent = `${frameValue}/${maxFrame}`;
  $("modelFrameSlider").max = maxFrame;
  $("modelFrameSlider").value = frameValue;
  $("modelFrameLabel").textContent = `${frameValue}/${maxFrame}`;
  $("rawMeta").textContent = metaSummary(state.raw);
  $("processedMeta").textContent = metaSummary(state.processed);
  const shared = boundsFor([state.raw, state.processed], $("rawCanvas"));
  drawSkeleton($("rawCanvas"), state.raw, shared);
  drawSkeleton($("processedCanvas"), state.processed, shared);
  vrmViewer?.setFrame?.(state.frame);
}

function previewParams(sample, fromArtifacts = true) {
  const params = new URLSearchParams({
    data_source: $("dataSourceSelect").value,
    dataset: $("datasetSelect").value,
    sample_id: sample.sample_id,
    from_artifacts: fromArtifacts ? "true" : "false",
  });
  const maxFrames = $("maxFramesInput").value.trim();
  if (maxFrames) params.set("max_frames", maxFrames);
  return params;
}

async function loadPreview(sample, persist = false) {
  if (persist) {
    const maxFrames = $("maxFramesInput").value.trim();
    await api("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data_source: $("dataSourceSelect").value,
        dataset: $("datasetSelect").value,
        sample_id: sample.sample_id,
        max_frames: maxFrames ? Number(maxFrames) : null,
        persist: true,
        skip_existing: false,
      }),
    });
  }

  const params = previewParams(sample, true);
  [state.raw, state.processed] = await Promise.all([
    api(`/api/preview/source?${params.toString()}`),
    api(`/api/preview/processed?${params.toString()}`),
  ]);
  state.frame = 0;
  if (state.processed?.motion) {
    vrmViewer?.setMotionPayload?.(state.processed);
  } else {
    try {
      const motion = await api(`/api/preview/motion?${params.toString()}`);
      vrmViewer?.setMotionPayload?.({ ...state.processed, motion });
    } catch {
      vrmViewer?.setMotionPayload?.(state.processed);
    }
  }
  renderPreview();
}

async function selectSample(sample, persist) {
  stopPlayback();
  state.selected = sample;
  $("sampleTitle").textContent = sample.sample_id;
  $("sampleText").textContent = sampleText(sample);
  renderSamples();
  $("rawMeta").textContent = "Loading raw preview...";
  $("processedMeta").textContent = "Loading processed preview...";
  try {
    await loadPreview(sample, persist);
  } catch (error) {
    $("processedMeta").textContent = String(error);
  }
}

async function loadSamples() {
  stopPlayback();
  const dataset = $("datasetSelect").value;
  const params = new URLSearchParams({
    data_source: $("dataSourceSelect").value,
    dataset,
    q: $("queryInput").value || "",
    limit: "80",
  });
  const payload = await api(`/api/samples?${params.toString()}`);
  state.samples = payload.items || [];
  state.selected = null;
  state.raw = null;
  state.processed = null;
  renderSamples();
  renderPreview();
  if (state.samples.length) {
    await selectSample(state.samples[0], false);
  }
}

function stopPlayback() {
  if (state.playbackTimer) {
    cancelAnimationFrame(state.playbackTimer);
    state.playbackTimer = null;
  }
  state.playing = false;
  $("playButton").textContent = "Play";
  $("modelPlayButton").textContent = "Play";
}

function playbackFps() {
  const candidates = [state.processed?.fps, state.raw?.fps]
    .map((value) => Number(value))
    .filter((value) => Number.isFinite(value) && value > 0);
  return candidates[0] || 30;
}

function startPlayback() {
  if (state.playbackTimer) return;
  state.playing = true;
  $("playButton").textContent = "Pause";
  $("modelPlayButton").textContent = "Pause";
  state.playbackStartMs = performance.now();
  state.playbackStartFrame = Math.floor(state.frame);
  const tick = (now) => {
    const maxFrames = Math.max(state.raw?.frame_count || 0, state.processed?.frame_count || 0);
    if (maxFrames) {
      const elapsedSec = Math.max(0, (now - state.playbackStartMs) / 1000);
      state.frame = Math.floor(state.playbackStartFrame + elapsedSec * playbackFps()) % maxFrames;
      renderPreview();
    }
    state.playbackTimer = requestAnimationFrame(tick);
  };
  state.playbackTimer = requestAnimationFrame(tick);
}

function togglePlayback() {
  if (state.playing) {
    stopPlayback();
    return;
  }
  startPlayback();
}

function renderSamples() {
  const list = $("sampleList");
  list.innerHTML = "";
  for (const sample of state.samples) {
    const item = document.createElement("button");
    item.className = `sample-item ${state.selected?.sample_id === sample.sample_id ? "active" : ""}`;
    item.innerHTML = `
      <strong>${sample.sample_id}</strong>
      <small>${sample.source_format}${sample.frame_count ? ` | ${sample.frame_count} frames` : ""}</small>
      <small>${sampleText(sample).slice(0, 140)}</small>
    `;
    item.addEventListener("click", () => selectSample(sample, false));
    list.appendChild(item);
  }
}

function resetPreviewView() {
  state.viewYaw = 0;
  state.viewPitch = 0.08;
  state.viewZoom = 1;
  renderPreview();
}

function attachPreviewViewControls(canvas) {
  canvas.addEventListener("pointerdown", (event) => {
    state.viewDragging = true;
    state.viewPointer = [event.clientX, event.clientY];
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!state.viewDragging) return;
    const dx = event.clientX - state.viewPointer[0];
    const dy = event.clientY - state.viewPointer[1];
    state.viewPointer = [event.clientX, event.clientY];
    state.viewYaw += dx * 0.01;
    state.viewPitch = Math.max(-1.35, Math.min(1.35, state.viewPitch + dy * 0.01));
    renderPreview();
  });
  canvas.addEventListener("pointerup", (event) => {
    state.viewDragging = false;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointercancel", () => {
    state.viewDragging = false;
  });
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    state.viewZoom = Math.max(0.45, Math.min(3.0, state.viewZoom * Math.exp(-event.deltaY * 0.001)));
    renderPreview();
  }, { passive: false });
  canvas.addEventListener("dblclick", resetPreviewView);
}

async function init() {
  const health = await api("/api/health");
  state.dataSources = health.available_data_sources || {};
  $("dataSourceSelect").innerHTML = Object.entries(state.dataSources)
    .map(([key, value]) => {
      const mark = value.exists ? "✓" : "✗";
      const shortPath = (value.raw_root || "").split(/[/\\]/).slice(-3).join("/");
      return `<option value="${key}" title="${value.raw_root || ''}">${mark} ${key} — ${value.label || key} [${shortPath}]</option>`;
    })
    .join("");
  const defaultSource = health.default_data_source;
  const firstExistingSource = Object.keys(state.dataSources).find((key) => state.dataSources[key].exists);
  $("dataSourceSelect").value =
    (defaultSource && state.dataSources[defaultSource]?.exists && defaultSource) || firstExistingSource || "full";
  const activeSource = state.dataSources[$("dataSourceSelect").value];
  $("health").textContent = `${$("dataSourceSelect").value}: ${activeSource?.raw_root || "?"}`;
  const datasets = await api(`/api/datasets?data_source=${encodeURIComponent($("dataSourceSelect").value)}`);
  state.datasets = datasets.datasets || [];
  $("datasetSelect").innerHTML = state.datasets.map((dataset) => `<option value="${dataset.key}">${dataset.name}</option>`).join("");
  $("datasetSelect").value = state.datasets.find((d) => d.key === "susuinteracts")?.key || state.datasets[0]?.key;
  vrmViewer = createVrmViewer({
    canvas: $("modelCanvas"),
    statusEl: $("modelStatus"),
    fileInput: $("modelFileInput"),
    resetButton: $("resetModelButton"),
  });
  applyTheme(localStorage.getItem(THEME_KEY) || "light");
  attachPreviewViewControls($("rawCanvas"));
  attachPreviewViewControls($("processedCanvas"));
  window.__vireaShowcase = {
    async loadSample({ dataSource = "demo", dataset, sampleId, maxFrames = "" }) {
      stopPlayback();
      if (dataSource && $("dataSourceSelect").value !== dataSource) {
        $("dataSourceSelect").value = dataSource;
        const info = state.dataSources[dataSource];
        $("health").textContent = `${dataSource}: ${info?.raw_root || "?"}`;
        const datasets = await api(`/api/datasets?data_source=${encodeURIComponent(dataSource)}`);
        state.datasets = datasets.datasets || [];
        $("datasetSelect").innerHTML = state.datasets.map((item) => `<option value="${item.key}">${item.name}</option>`).join("");
      }
      if (dataset) $("datasetSelect").value = dataset;
      $("maxFramesInput").value = maxFrames ? String(maxFrames) : "";
      state.selected = { sample_id: sampleId };
      state.samples = [state.selected];
      $("sampleTitle").textContent = sampleId;
      $("sampleText").textContent = "";
      renderSamples();
      await loadPreview(state.selected, false);
      return {
        dataset: $("datasetSelect").value,
        sampleId,
        frames: Math.max(state.raw?.frame_count || 0, state.processed?.frame_count || 0),
      };
    },
    setFrame(frame) {
      stopPlayback();
      state.frame = Math.max(0, Number(frame) || 0);
      renderPreview();
    },
  };
  await loadSamples();
}

$("searchButton").addEventListener("click", loadSamples);
$("datasetSelect").addEventListener("change", loadSamples);
$("dataSourceSelect").addEventListener("change", async () => {
  const src = $("dataSourceSelect").value;
  const info = state.dataSources[src];
  $("health").textContent = `${src}: ${info?.raw_root || "?"}`;
  stopPlayback();
  await loadSamples();
});
$("queryInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadSamples();
});
$("frameSlider").addEventListener("input", (event) => {
  stopPlayback();
  state.frame = Number(event.target.value);
  renderPreview();
});
$("playButton").addEventListener("click", togglePlayback);
$("modelPlayButton").addEventListener("click", togglePlayback);
$("modelFrameSlider").addEventListener("input", (event) => {
  stopPlayback();
  state.frame = Number(event.target.value);
  renderPreview();
});
$("themeToggle").addEventListener("click", () => {
  const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  applyTheme(current === "dark" ? "light" : "dark");
  renderPreview();
});
$("persistButton").addEventListener("click", () => {
  if (state.selected) selectSample(state.selected, true);
});
$("showTrailsToggle").addEventListener("change", (event) => {
  state.showTrails = event.target.checked;
  renderPreview();
});
$("showHandsToggle").addEventListener("change", (event) => {
  state.showHands = event.target.checked;
  renderPreview();
});

init().catch((error) => {
  $("health").textContent = String(error);
});

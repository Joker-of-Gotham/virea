import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMHumanBoneList, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import {
  buildHumanoidSpaceAlignment,
  invertQuatArray,
  multiplyQuatArray,
  normalizeQuatArray,
} from "./vrm-canonical-alignment.js";

const ROOT_NAMES = ["hips", "pelvis", "root"];
const CANONICAL_PARENT = {
  spine: "hips",
  chest: "spine",
  upperChest: "chest",
  neck: "upperChest",
  head: "neck",
  leftShoulder: "upperChest",
  leftUpperArm: "leftShoulder",
  leftLowerArm: "leftUpperArm",
  leftHand: "leftLowerArm",
  rightShoulder: "upperChest",
  rightUpperArm: "rightShoulder",
  rightLowerArm: "rightUpperArm",
  rightHand: "rightLowerArm",
  leftUpperLeg: "hips",
  leftLowerLeg: "leftUpperLeg",
  leftFoot: "leftLowerLeg",
  leftToes: "leftFoot",
  rightUpperLeg: "hips",
  rightLowerLeg: "rightUpperLeg",
  rightFoot: "rightLowerLeg",
  rightToes: "rightFoot",
  leftThumbProximal: "leftHand",
  leftThumbIntermediate: "leftThumbProximal",
  leftThumbDistal: "leftThumbIntermediate",
  leftIndexProximal: "leftHand",
  leftIndexIntermediate: "leftIndexProximal",
  leftIndexDistal: "leftIndexIntermediate",
  leftMiddleProximal: "leftHand",
  leftMiddleIntermediate: "leftMiddleProximal",
  leftMiddleDistal: "leftMiddleIntermediate",
  leftRingProximal: "leftHand",
  leftRingIntermediate: "leftRingProximal",
  leftRingDistal: "leftRingIntermediate",
  leftLittleProximal: "leftHand",
  leftLittleIntermediate: "leftLittleProximal",
  leftLittleDistal: "leftLittleIntermediate",
  rightThumbProximal: "rightHand",
  rightThumbIntermediate: "rightThumbProximal",
  rightThumbDistal: "rightThumbIntermediate",
  rightIndexProximal: "rightHand",
  rightIndexIntermediate: "rightIndexProximal",
  rightIndexDistal: "rightIndexIntermediate",
  rightMiddleProximal: "rightHand",
  rightMiddleIntermediate: "rightMiddleProximal",
  rightMiddleDistal: "rightMiddleIntermediate",
  rightRingProximal: "rightHand",
  rightRingIntermediate: "rightRingProximal",
  rightRingDistal: "rightRingIntermediate",
  rightLittleProximal: "rightHand",
  rightLittleIntermediate: "rightLittleProximal",
  rightLittleDistal: "rightLittleIntermediate",
};

function finitePoint(point) {
  return (
    Array.isArray(point) &&
    point.length >= 3 &&
    Number.isFinite(point[0]) &&
    Number.isFinite(point[1]) &&
    Number.isFinite(point[2])
  );
}

function disposeMaterial(material) {
  if (!material) return;
  if (Array.isArray(material)) {
    material.forEach(disposeMaterial);
    return;
  }
  for (const value of Object.values(material)) {
    if (value?.isTexture) value.dispose();
  }
  material.dispose?.();
}

function disposeObject(object) {
  object.traverse?.((child) => {
    child.geometry?.dispose?.();
    disposeMaterial(child.material);
  });
}

function clearGroup(group) {
  for (const child of [...group.children]) {
    group.remove(child);
    disposeObject(child);
  }
}

function payloadRootIndex(payload) {
  const names = payload?.skeleton?.joint_names || [];
  for (const name of ROOT_NAMES) {
    const index = names.findIndex((item) => String(item).toLowerCase() === name);
    if (index >= 0) return index;
  }
  return 0;
}

function motionBounds(payload) {
  const frames = payload?.frames?.positions || [];
  if (!frames.length) {
    return { center: new THREE.Vector3(0, 0.95, 0), radius: 2.1 };
  }
  const box = new THREE.Box3();
  const point = new THREE.Vector3();
  const stride = Math.max(1, Math.floor(frames.length / 80));
  for (let frameIndex = 0; frameIndex < frames.length; frameIndex += stride) {
    for (const raw of frames[frameIndex]) {
      if (!finitePoint(raw)) continue;
      point.set(raw[0], raw[1], raw[2]);
      box.expandByPoint(point);
    }
  }
  if (box.isEmpty()) return { center: new THREE.Vector3(0, 0.95, 0), radius: 2.1 };
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  return { center, radius: Math.max(size.x, size.y, size.z, 1.6) };
}

function fitStaticScene(scene) {
  const box = new THREE.Box3().setFromObject(scene);
  if (box.isEmpty()) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const scale = 1.75 / Math.max(size.x, size.y, size.z, 1e-4);
  scene.position.sub(center);
  scene.scale.setScalar(scale);
}

function resolveVrmBodyOffset(vrm) {
  const rawHips = vrm?.humanoid?.getRawBoneNode?.("hips");
  return rawHips ? rawHips.position.clone().multiplyScalar(-1) : new THREE.Vector3(0, 0, 0);
}

export function createVrmViewer({ canvas, statusEl, fileInput, resetButton }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xfbf7ed);

  const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 120);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.target.set(0, 0.9, 0);

  scene.add(new THREE.HemisphereLight(0xfff7e2, 0x20343c, 1.7));
  const key = new THREE.DirectionalLight(0xfff0cf, 2.0);
  key.position.set(3.5, 5.0, 4.0);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xbfe6ff, 1.0);
  rim.position.set(-4.0, 2.5, -3.0);
  scene.add(rim);

  const grid = new THREE.GridHelper(12, 24, 0x8aa19a, 0xd4cabc);
  grid.material.transparent = true;
  grid.material.opacity = 0.45;
  scene.add(grid);

  const motionRoot = new THREE.Group();
  scene.add(motionRoot);

  const canonicalRoot = new THREE.Group();
  motionRoot.add(canonicalRoot);

  const staticRoot = new THREE.Group();
  scene.add(staticRoot);

  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));

  const state = {
    payload: null,
    motion: null,
    frame: 0,
    vrm: null,
    vrmWorldAlignment: null,
    staticScene: null,
    currentFileName: "",
    theme: "light",
  };

  function setStatus(message) {
    if (statusEl) statusEl.textContent = message || "";
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, 1);
    camera.updateProjectionMatrix();
  }

  function resetView() {
    const { center, radius } = motionBounds(state.payload);
    controls.target.copy(center);
    camera.position.set(center.x - radius * 0.95, center.y + radius * 0.55, center.z + radius * 2.1);
    camera.near = 0.01;
    camera.far = Math.max(80, radius * 20);
    camera.updateProjectionMatrix();
    controls.update();
  }

  function clearCurrentModel() {
    if (state.vrm?.scene) {
      disposeObject(state.vrm.scene);
    }
    if (state.staticScene) {
      disposeObject(state.staticScene);
    }
    clearGroup(canonicalRoot);
    clearGroup(staticRoot);
    motionRoot.position.set(0, 0, 0);
    motionRoot.quaternion.identity();
    canonicalRoot.position.set(0, 0, 0);
    canonicalRoot.quaternion.identity();
    state.vrm = null;
    state.vrmWorldAlignment = null;
    state.staticScene = null;
    state.currentFileName = "";
  }

  function poseQuat(q) {
    return normalizeQuatArray(q);
  }

  function conjugateQuatByBasis(q, basis) {
    const basisN = normalizeQuatArray(basis);
    return multiplyQuatArray(multiplyQuatArray(basisN, q), invertQuatArray(basisN));
  }

  function captureRawHumanoidPositionMap(vrm, localRoot = motionRoot) {
    const humanoid = vrm?.humanoid;
    if (!humanoid) return {};
    const world = new THREE.Vector3();
    const positions = {};
    for (const boneName of VRMHumanBoneList) {
      const bone = humanoid.getRawBoneNode(boneName);
      if (!bone) continue;
      bone.getWorldPosition(world);
      localRoot.worldToLocal(world);
      positions[boneName] = [world.x, world.y, world.z];
    }
    return positions;
  }

  function reconstructTargetRestPositionMap(motion) {
    const restBones = motion?.rest_bones || [];
    const offsets = motion?.rest_offsets || {};
    if (!restBones.length) return null;
    const positions = {};
    for (const boneName of restBones) {
      if (boneName === "hips") {
        positions.hips = [0, 0, 0];
        continue;
      }
      const parent = CANONICAL_PARENT[boneName];
      const parentPosition = parent ? positions[parent] : null;
      const offset = offsets[boneName];
      if (!parentPosition || !finitePoint(offset)) continue;
      positions[boneName] = [
        parentPosition[0] + offset[0],
        parentPosition[1] + offset[1],
        parentPosition[2] + offset[2],
      ];
    }
    return positions;
  }

  function applyVrmCanonicalWorldAlignment(vrm = state.vrm) {
    if (!vrm) return null;
    canonicalRoot.quaternion.identity();
    motionRoot.updateMatrixWorld(true);
    const rawPositions = captureRawHumanoidPositionMap(vrm, motionRoot);
    const targetRestPositions = reconstructTargetRestPositionMap(state.motion);
    const alignment = targetRestPositions
      ? buildHumanoidSpaceAlignment(rawPositions, targetRestPositions)
      : null;
    if (!alignment?.alignment_quaternion) {
      state.vrmWorldAlignment = null;
      return null;
    }
    const q = alignment.alignment_quaternion;
    canonicalRoot.quaternion.set(q[0], q[1], q[2], q[3]).normalize();
    motionRoot.updateMatrixWorld(true);
    state.vrmWorldAlignment = alignment;
    return alignment;
  }

  function poseObjectFromFrame(frame) {
    const motion = state.motion;
    if (!motion) return {};
    const safeFrame = Math.max(0, Math.min(Math.floor(frame), motion.frame_count - 1));
    const pose = {};
    const canonicalToVrm = motion.canonical_to_vrm || {};
    const alignQuat = state.vrmWorldAlignment?.alignment_quaternion || null;
    const alignBasis = alignQuat ? invertQuatArray(normalizeQuatArray(alignQuat)) : null;
    (motion.core_bones || []).forEach((boneName, boneIndex) => {
      const rotation = motion.core_quaternions?.[safeFrame]?.[boneIndex];
      if (!rotation) return;
      const vrmBoneName = canonicalToVrm[boneName] || boneName;
      pose[vrmBoneName] = { rotation: alignBasis ? conjugateQuatByBasis(rotation, alignBasis) : poseQuat(rotation) };
    });
    (motion.hand_bones || []).forEach((boneName, boneIndex) => {
      const rotation = motion.hand_quaternions?.[safeFrame]?.[boneIndex];
      if (!rotation) return;
      const vrmBoneName = canonicalToVrm[boneName] || boneName;
      pose[vrmBoneName] = { rotation: alignBasis ? conjugateQuatByBasis(rotation, alignBasis) : poseQuat(rotation) };
    });
    return pose;
  }

  function applyVrmFrame(frame) {
    if (!state.vrm || !state.motion) return;
    const motion = state.motion;
    const safeFrame = Math.max(0, Math.min(Math.floor(frame), motion.frame_count - 1));
    const translation = motion.root_translation?.[safeFrame] || [0, 0, 0];
    const rotation = normalizeQuatArray(motion.root_rotation?.[safeFrame] || [0, 0, 0, 1]);
    motionRoot.position.set(translation[0], translation[1], translation[2]);
    motionRoot.quaternion.set(rotation[0], rotation[1], rotation[2], rotation[3]).normalize();
    state.vrm.humanoid.resetNormalizedPose?.();
    const pose = poseObjectFromFrame(safeFrame);
    if (typeof state.vrm.humanoid.setNormalizedPose === "function") {
      state.vrm.humanoid.setNormalizedPose(pose);
    } else if (typeof state.vrm.humanoid.setRawPose === "function") {
      state.vrm.humanoid.setRawPose(pose);
    }
    state.vrm.humanoid.update?.();
    state.vrm.update?.(0);
    state.vrm.scene.updateMatrixWorld(true);
  }

  function applyFrame() {
    applyVrmFrame(state.frame);
  }

  async function loadModel(file) {
    clearCurrentModel();
    if (!file) {
      setStatus("No model loaded. Load a .vrm to preview the processed motion on the avatar.");
      return;
    }
    state.currentFileName = file.name;
    setStatus(`Loading ${file.name} ...`);
    const url = URL.createObjectURL(file);
    try {
      const gltf = await loader.loadAsync(url);
      const vrm = gltf.userData.vrm || null;
      if (vrm) {
        VRMUtils.removeUnnecessaryVertices(gltf.scene);
        VRMUtils.removeUnnecessaryJoints(gltf.scene);
        VRMUtils.rotateVRM0?.(vrm);
        vrm.scene.rotation.set(0, 0, 0);
        vrm.scene.position.copy(resolveVrmBodyOffset(vrm));
        canonicalRoot.add(vrm.scene);
        state.vrm = vrm;
        applyVrmCanonicalWorldAlignment(vrm);
        applyFrame();
        const boneCount = VRMHumanBoneList.filter((boneName) => vrm.humanoid?.getRawBoneNode?.(boneName)).length;
        const aligned = state.vrmWorldAlignment ? "aligned to processed VRM rest" : "loaded without rest alignment";
        setStatus(`${file.name} loaded as VRM. Humanoid bones: ${boneCount}; ${aligned}. Drag to orbit; wheel to zoom.`);
      } else {
        fitStaticScene(gltf.scene);
        staticRoot.add(gltf.scene);
        state.staticScene = gltf.scene;
        setStatus(`${file.name} loaded as static GLB/GLTF. It has no VRM humanoid, so motion retargeting is not applied.`);
      }
      resetView();
    } catch (error) {
      clearCurrentModel();
      setStatus(`Failed to load ${file.name}: ${error?.message || error}`);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  function setMotionPayload(payload) {
    state.payload = payload || null;
    state.motion = payload?.motion || null;
    state.frame = 0;
    applyVrmCanonicalWorldAlignment(state.vrm);
    resetView();
    applyFrame();
    if (!state.motion) {
      setStatus("Processed preview loaded, but no VRM motion payload is available.");
    }
  }

  function setFrame(frame) {
    state.frame = Math.max(0, Number(frame) || 0);
    applyFrame();
  }

  function setTheme(theme) {
    state.theme = theme === "dark" ? "dark" : "light";
    scene.background = new THREE.Color(state.theme === "dark" ? 0x111820 : 0xfbf7ed);
    grid.material.opacity = state.theme === "dark" ? 0.32 : 0.45;
  }

  function render() {
    resize();
    controls.update();
    renderer.render(scene, camera);
    window.requestAnimationFrame(render);
  }

  fileInput?.addEventListener("change", async (event) => {
    await loadModel(event.target.files?.[0] || null);
  });
  resetButton?.addEventListener("click", resetView);
  window.addEventListener("resize", resize);

  setStatus("three-vrm viewer ready. Load a .vrm to drive it with the processed motion.");
  resetView();
  window.requestAnimationFrame(render);

  return { loadModel, resetView, setMotionPayload, setFrame, setTheme };
}

/**
 * Sound System Module
 * Shared sound management across handover.html and scan.html
 */

// Sound file URLs - will be populated by Flask url_for
let STATIC_AUDIO_URLS = {};

// Sound mapping
const SND_MAP = {
  ok: "ok.mp3",
  err: "error.mp3",
  cancel: "cancel.mp3",
  sys_success: "sys_success.mp3",
  sys_error: "sys_error.mp3"
};

// Preloaded audio elements
const _audioEls = new Map();

// Beep fallback for when files fail
const BEEP_OK = "UklGRoQAAABXQVZFZm10IBAAAAABAAEARKwAABCiAAACABYAAABhYWFhYWFhYQAA";
const BEEP_ERR = "UklGRoQAAABXQVZFZm10IBAAAAABAAEARKwAABCiAAACABYAAABhZmZhZmZhZgAA";

function _beep(ok = true) {
  const a = new Audio("data:audio/wav;base64," + (ok ? BEEP_OK : BEEP_ERR));
  a.play().catch(() => {});
}

// Audio unlock state
let _audioUnlocked = false;

/**
 * Initialize sound system with Flask-generated URLs
 * @param {Object} audioUrls - Object with filename -> URL mapping
 */
export function initSounds(audioUrls) {
  STATIC_AUDIO_URLS = audioUrls;

  // Preload all audio files
  Object.entries(STATIC_AUDIO_URLS).forEach(([name, url]) => {
    const a = new Audio(url);
    a.preload = "auto";
    _audioEls.set(name, a);
  });

  // Setup unlock listeners
  window.addEventListener("click", unlockAudioOnce, { once: true });
  window.addEventListener("keydown", unlockAudioOnce, { once: true });
}

/**
 * Unlock audio autoplay (required by browsers)
 */
async function unlockAudioOnce() {
  if (_audioUnlocked) return;
  _audioUnlocked = true;

  // 1) Try WebAudio unlock first
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      const actx = new AudioCtx();
      if (actx.state === "suspended" && actx.resume) {
        await actx.resume().catch(() => {});
      }
      const buffer = actx.createBuffer(1, 1, actx.sampleRate);
      const src = actx.createBufferSource();
      src.buffer = buffer;
      src.connect(actx.destination);
      src.start(0);
      return;
    }
  } catch (e) {
    // Continue to fallback
  }

  // 2) Fallback: silent play/pause all audio
  for (const a of _audioEls.values()) {
    try {
      const prevMuted = a.muted;
      const prevVolume = a.volume;
      a.muted = true;
      a.volume = 0;
      await a.play().then(() => a.pause()).catch(() => {});
      a.currentTime = 0;
      a.muted = prevMuted;
      a.volume = prevVolume;
    } catch (e) {}
  }
}

/**
 * Play sound by filename
 * @param {string} name - Sound filename (e.g., "ok.mp3")
 */
function playByName(name) {
  const a = _audioEls.get(name);
  if (!a) return _beep(false);
  a.currentTime = 0;
  a.play().catch(() => {});
}

// Public API functions
export const playOk = () => playByName(SND_MAP.ok);
export const playErr = () => playByName(SND_MAP.err);
export const playCancel = () => playByName(SND_MAP.cancel);
export const playSysOk = () => playByName(SND_MAP.sys_success);
export const playSysErr = () => playByName(SND_MAP.sys_error);

// For backward compatibility - global functions
window.playOk = playOk;
window.playErr = playErr;
window.playCancel = playCancel;
window.playSysOk = playSysOk;
window.playSysErr = playSysErr;

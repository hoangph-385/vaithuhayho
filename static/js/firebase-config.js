/**
 * Firebase Configuration Module
 * Shared across handover.html and scan.html
 */

// Firebase configs for different projects
export const FIREBASE_CONFIGS = {
  handover: {
    apiKey: "AIzaSyB0JkBQG2tYpMF1_tBFJfUk6YOF8OMYd8w",
    authDomain: "handover-4.firebaseapp.com",
    databaseURL: "https://handover-4-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "handover-4",
    storageBucket: "handover-4.firebasestorage.app",
    messagingSenderId: "746859503766",
    appId: "1:746859503766:web:b51dc1506a1b80fef88d81"
  },

  scan: {
    apiKey: "AIzaSyAWB7MMNgLhmTJgDhV8WerUFqqGBdGwn0w",
    authDomain: "data-scan-tool.firebaseapp.com",
    databaseURL: "https://data-scan-tool-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "data-scan-tool",
    storageBucket: "data-scan-tool.appspot.com",
    messagingSenderId: "604963527207",
    appId: "1:604963527207:web:82877194174efbc7a3cc02"
  }
};

// Initialize Firebase app for specific project
export async function initFirebase(projectType = 'handover') {
  const { initializeApp, getApps } = await import("https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js");
  const { getDatabase, ref, onValue, push, set, remove, get, goOffline, goOnline } = await import("https://www.gstatic.com/firebasejs/10.12.2/firebase-database.js");

  const config = FIREBASE_CONFIGS[projectType];
  if (!config) {
    throw new Error(`Unknown project type: ${projectType}`);
  }

  // Avoid "Firebase App already exists" error
  const app = getApps().length ? getApps()[0] : initializeApp(config);
  const database = getDatabase(app);

  // Expose databaseURL to window for compatibility with existing RTDB helper functions
  window.__firebaseDB = window.__firebaseDB || {};
  window.__firebaseDB.databaseURL = config.databaseURL;

  return {
    app,
    db: database,  // alias for compatibility
    database,
    databaseURL: config.databaseURL,
    ref,
    onValue,
    push,
    set,
    remove,
    get,
    goOffline,
    goOnline
  };
}

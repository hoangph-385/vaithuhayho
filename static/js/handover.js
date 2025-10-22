/**
 * Handover Tool - JavaScript Module
 * Firebase integration and UI logic
 */

// ===== Firebase Configuration =====
const firebaseConfig = {
  apiKey: "AIzaSyCdSInR5JXWsFCZl3ygdoEeSRra6_wGrW4",
  authDomain: "handover-4.firebaseapp.com",
  databaseURL: "https://handover-4-default-rtdb.asia-southeast1.firebasedatabase.app",
  projectId: "handover-4",
  storageBucket: "handover-4.firebasestorage.app",
  messagingSenderId: "935608155206",
  appId: "1:935608155206:web:4abc6a60e1736399571e47",
  measurementId: "G-FVKZLCE7DB"
};

// ===== Global State =====
window.HandoverApp = {
  db: null,
  ALL_EVENTS: {},
  CANCEL_MAP: {},
  currentBatchByCh: { SPX: 1, GHN: 1 },
  scanPageIndex: 1,
  cancelPageIndex: 1,
  SELECTED_KEY: '',
  SELECTED_ISO: '',
  connected: false,
  PAGE_SIZE: 100,

  // Initialize
  init: async function() {
    console.log('[Handover] Initializing...');
    this.SELECTED_KEY = this.today();
    this.SELECTED_ISO = this.todayISO();

    // Setup date picker
    const datePicker = document.getElementById('datePicker');
    if (datePicker) {
      datePicker.value = this.SELECTED_ISO;
    }

    // Initialize Firebase
    await this.initFirebase();

    // Setup UI
    this.setupEventListeners();
    this.watchConnectivity();
    this.bindAllListenersFor(this.SELECTED_KEY);

    console.log('[Handover] Initialized successfully');
  },

  // Date helpers
  today: function() {
    const d = new Date();
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    return `${dd}-${mm}-${yyyy}`;
  },

  todayISO: function() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${dd}`;
  },

  isoToKey: function(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return this.today();
    const [y, m, d] = iso.split('-');
    return `${d}-${m}-${y}`;
  },

  // Notice/Alert
  notice: function(msg, kind = 'info', timeout = 6000) {
    const bar = document.getElementById('notice');
    if (!bar) return;

    const styles = {
      info: 'color:#31708f;',
      success: 'color:#3c763d;font-weight:600;',
      warning: 'color:#8a6d3b;font-weight:600;',
      error: 'color:#a94442;font-weight:600;'
    };

    bar.style.cssText += styles[kind] || styles.info;
    bar.textContent = msg || '';

    if (timeout > 0) {
      setTimeout(() => bar.textContent = '', timeout);
    }
  }
};

// ===== Initialize on page load =====
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => HandoverApp.init());
} else {
  HandoverApp.init();
}

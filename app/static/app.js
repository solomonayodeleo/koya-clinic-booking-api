let currentApiKey = sessionStorage.getItem('X_API_KEY') || '';
let currentSlots = [];
let myBookingsCursor = null;
let currentLookupEmail = '';

// DOM Elements
const slotsContainer = document.getElementById('slots-container');
const providerSelect = document.getElementById('provider-select');
const dateFilter = document.getElementById('date-filter');
const btnClearDate = document.getElementById('btn-clear-date');
const timeFilter = document.getElementById('time-filter');
const slotsSummary = document.getElementById('slots-summary');
const btnRefreshSlots = document.getElementById('btn-refresh-slots');
const btnQuickReset = document.getElementById('btn-quick-reset');
const toastEl = document.getElementById('toast');

const keyModal = document.getElementById('key-modal');
const btnToggleKey = document.getElementById('btn-toggle-key');
const btnCloseKeyModal = document.getElementById('btn-close-key-modal');
const inputApiKey = document.getElementById('input-api-key');
const btnSaveKey = document.getElementById('btn-save-key');

const bookingModal = document.getElementById('booking-modal');
const btnCloseBookingModal = document.getElementById('btn-close-booking-modal');
const btnCancelModal = document.getElementById('btn-cancel-modal');
const formBookSlot = document.getElementById('form-book-slot');
const modalSlotId = document.getElementById('modal-slot-id');
const modalSlotProvider = document.getElementById('modal-slot-provider');
const modalSlotTime = document.getElementById('modal-slot-time');
const modalError = document.getElementById('modal-error');

const confirmationModal = document.getElementById('confirmation-modal');
const btnDismissConfirmation = document.getElementById('btn-dismiss-confirmation');
const confirmId = document.getElementById('confirm-id');
const confirmProvider = document.getElementById('confirm-provider');
const confirmTime = document.getElementById('confirm-time');
const confirmName = document.getElementById('confirm-name');
const confirmEmail = document.getElementById('confirm-email');

const formLookup = document.getElementById('form-lookup');
const lookupEmailInput = document.getElementById('lookup-email');
const myBookingsContainer = document.getElementById('my-bookings-container');
const btnLoadMore = document.getElementById('btn-load-more');
const paginationControls = document.getElementById('pagination-controls');

// Helper to format ISO dates
function formatDateTime(isoString) {
  try {
    const d = new Date(isoString);
    return d.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    });
  } catch (e) {
    return isoString;
  }
}

function showToast(message, type = 'success') {
  toastEl.textContent = message;
  toastEl.className = `toast toast-${type}`;
  toastEl.classList.remove('hidden');
  setTimeout(() => {
    toastEl.classList.add('hidden');
  }, 4000);
}

// API Helper with X-API-Key header
async function apiFetch(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-API-Key': currentApiKey,
    ...(options.headers || {}),
  };

  const response = await fetch(endpoint, {
    ...options,
    headers,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(data.error || `Request failed with status ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return data;
}

function getLocalDateKey(isoString) {
  const d = new Date(isoString);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function matchesTimePeriod(isoString, period) {
  if (!period) return true;
  const hour = new Date(isoString).getHours();
  if (period === 'morning') return hour < 12;
  if (period === 'afternoon') return hour >= 12 && hour < 17;
  if (period === 'evening') return hour >= 17;
  return true;
}

function applySlotFilters() {
  const now = new Date();
  const weekEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7);
  const selectedDate = dateFilter.value;
  const selectedTime = timeFilter.value;

  const selectedProvider = providerSelect.value;
  const filteredSlots = currentSlots.filter((slot) => {
    const start = Date.parse(slot.start);
    const inDateRange = selectedDate
      ? getLocalDateKey(slot.start) === selectedDate
      : start < weekEnd;
    return start > now && inDateRange &&
      (!selectedProvider || slot.provider === selectedProvider) &&
      matchesTimePeriod(slot.start, selectedTime);
  });

  btnClearDate.classList.toggle('hidden', !selectedDate);
  const count = filteredSlots.length;
  const dateScope = selectedDate ? '' : ' in the next 7 days';
  slotsSummary.textContent = `${count} matching upcoming ${count === 1 ? 'slot' : 'slots'}${dateScope}`;
  slotsSummary.classList.remove('hidden');
  renderSlots(filteredSlots, Boolean(selectedDate), Boolean(selectedProvider || selectedTime));
}

async function loadSlots() {
  if (!currentApiKey) {
    slotsSummary.classList.add('hidden');
    slotsContainer.innerHTML = '<div class="empty-state">Enter your API key to view appointment slots.</div>';
    return;
  }

  slotsContainer.innerHTML = '<div class="loading-state">Loading appointment slots...</div>';
  try {
    const data = await apiFetch('/slots');
    currentSlots = (data.slots || []).sort((a, b) => Date.parse(a.start) - Date.parse(b.start));

    const previousProvider = providerSelect.value;
    const providers = [...new Set(currentSlots.map((slot) => slot.provider))].sort();
    providerSelect.innerHTML = '<option value="">All Specialists</option>';
    for (const provider of providers) {
      providerSelect.add(new Option(provider, provider));
    }
    if (providers.includes(previousProvider)) providerSelect.value = previousProvider;

    applySlotFilters();
  } catch (err) {
    slotsSummary.classList.add('hidden');
    slotsContainer.innerHTML = `
      <div class="empty-state" style="color: var(--danger);">
        Failed to load slots: ${escapeHtml(err.message)}<br>
        <button class="btn btn-secondary" style="margin-top: 12px;" onclick="loadSlots()">Retry</button>
      </div>`;
  }
}

function renderSlots(slots, hasDateFilter, hasOtherFilters) {
  if (!slots.length) {
    const message = hasDateFilter
      ? 'No upcoming slots match your filters on this date.'
      : 'No upcoming slots match your filters.';
    const action = hasDateFilter
      ? '<button type="button" class="btn btn-secondary" data-clear-date>Show Next 7 Days</button>'
      : '';
    slotsContainer.innerHTML = `
      <div class="empty-state">
        ${hasDateFilter || hasOtherFilters ? message : 'No upcoming appointment slots in the next 7 days.'}
        ${action}
      </div>`;
    return;
  }

  slotsContainer.innerHTML = slots
    .map(
      (slot) => `
    <div class="slot-card">
      <div>
        <div class="slot-header">
          <div class="slot-provider">${escapeHtml(slot.provider)}</div>
          <span class="status-badge ${slot.available ? 'status-available' : 'status-booked'}">
            ${slot.available ? '● Available' : 'Booked'}
          </span>
        </div>
        <div class="slot-time">
          🕒 ${formatDateTime(slot.start)}
        </div>
      </div>
      <div>
        ${
          slot.available
            ? `<button class="btn btn-primary" style="width: 100%;" data-slot-id="${escapeHtml(slot.id)}">Book Appointment</button>`
            : `<button class="btn btn-secondary" style="width: 100%; opacity: 0.6; cursor: not-allowed;" disabled>Slot Unavailable</button>`
        }
      </div>
    </div>
  `
    )
    .join('');
}

function escapeHtml(str) {
  return str.replace(/[&<>'"]/g, (tag) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag));
}

slotsContainer.addEventListener('click', (event) => {
  if (event.target.closest('button[data-clear-date]')) {
    clearDateFilter();
    return;
  }
  const button = event.target.closest('button[data-slot-id]');
  if (button) openBookingModal(button.dataset.slotId);
});

// Booking Modal Logic
let bookingAttempt = null;

function openBookingModal(slotId) {
  const slot = currentSlots.find((s) => s.id === slotId);
  if (!slot) return;

  bookingAttempt = null;
  modalSlotId.value = slot.id;
  modalSlotProvider.textContent = slot.provider;
  modalSlotTime.textContent = `${formatDateTime(slot.start)} - ${formatDateTime(slot.end)}`;
  modalError.classList.add('hidden');
  modalError.textContent = '';
  document.getElementById('patient-name').value = '';
  document.getElementById('patient-email').value = '';

  bookingModal.classList.remove('hidden');
}

function closeBookingModal() {
  bookingModal.classList.add('hidden');
}

formBookSlot.addEventListener('submit', async (e) => {
  e.preventDefault();
  const slotId = modalSlotId.value;
  const name = document.getElementById('patient-name').value.trim();
  const email = document.getElementById('patient-email').value.trim();

  const btnConfirm = document.getElementById('btn-confirm-booking');
  btnConfirm.disabled = true;
  btnConfirm.textContent = 'Booking...';

  try {
    const body = JSON.stringify({ slot_id: slotId, name, email });
    if (bookingAttempt?.body !== body) {
      bookingAttempt = { body, key: crypto.randomUUID() };
    }
    const booking = await apiFetch('/bookings', {
      method: 'POST',
      headers: { 'Idempotency-Key': bookingAttempt.key },
      body,
    });

    closeBookingModal();

    // Show Confirmation
    const slot = currentSlots.find((s) => s.id === slotId);
    confirmId.textContent = booking.id;
    confirmProvider.textContent = slot ? slot.provider : 'Specialist';
    confirmTime.textContent = slot ? `${formatDateTime(slot.start)}` : 'Scheduled Time';
    confirmName.textContent = booking.name;
    confirmEmail.textContent = booking.email;

    confirmationModal.classList.remove('hidden');
    loadSlots();
  } catch (err) {
    if (err.status >= 400 && err.status < 500) bookingAttempt = null;
    modalError.textContent = err.message;
    modalError.classList.remove('hidden');
  } finally {
    btnConfirm.disabled = false;
    btnConfirm.textContent = 'Confirm Booking';
  }
});

btnDismissConfirmation.addEventListener('click', () => {
  confirmationModal.classList.add('hidden');
});

// Quick Reset Demo Data
async function triggerQuickReset() {
  if (!currentApiKey || !confirm('Replace the demo slots and delete all existing demo bookings?')) return;
  try {
    const now = new Date();
    const providers = [
      'Dr Ade (Cardiologist)',
      'Dr Fatima (Pediatrician)',
      'Dr John (General Physician)',
    ];
    const totalDays = 35;
    const slots = [];

    for (let day = 1; day <= totalDays; day++) {
      const slotHours = [9, 12, day % 2 ? 15 : 17];
      for (let i = 0; i < providers.length; i++) {
        const provider = providers[(day + i) % providers.length];
        const hour = slotHours[i];
        const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() + day, hour, 0, 0, 0);
        const end = new Date(start.getTime() + 60 * 60 * 1000);
        slots.push({
          id: `slot-d${day}-${i + 1}`,
          provider,
          start: start.toISOString(),
          end: end.toISOString(),
        });
      }
    }

    await apiFetch('/reset', {
      method: 'POST',
      body: JSON.stringify({ slots }),
    });

    showToast(`Demo slots reset successfully! Created ${slots.length} slots over the next ${totalDays} days.`);
    await loadSlots();
  } catch (err) {
    showToast(`Reset failed: ${err.message}`, 'error');
  }
}

function clearDateFilter() {
  dateFilter.value = '';
  applySlotFilters();
  dateFilter.focus();
}

btnQuickReset.addEventListener('click', triggerQuickReset);
btnRefreshSlots.addEventListener('click', loadSlots);
providerSelect.addEventListener('change', applySlotFilters);
btnClearDate.addEventListener('click', clearDateFilter);
dateFilter.addEventListener('change', applySlotFilters);
timeFilter.addEventListener('change', applySlotFilters);

// Tab Navigation
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.add('hidden'));

    btn.classList.add('active');
    const target = document.getElementById(btn.dataset.tab);
    if (target) target.classList.remove('hidden');
  });
});

// My Bookings Tab Logic (Level 4 Pagination & Level 3 Cancellation)
formLookup.addEventListener('submit', async (e) => {
  e.preventDefault();
  currentLookupEmail = lookupEmailInput.value.trim();
  myBookingsCursor = null;
  myBookingsContainer.innerHTML = '<div class="loading-state">Searching bookings...</div>';
  await fetchMyBookings(false);
});

btnLoadMore.addEventListener('click', async () => {
  if (myBookingsCursor) {
    await fetchMyBookings(true);
  }
});

async function fetchMyBookings(isAppend = false) {
  try {
    let url = `/bookings?email=${encodeURIComponent(currentLookupEmail)}&limit=4`;
    if (myBookingsCursor) {
      url += `&cursor=${encodeURIComponent(myBookingsCursor)}`;
    }

    const res = await apiFetch(url);
    const bookings = res.bookings || [];
    myBookingsCursor = res.next_cursor;

    if (!isAppend && bookings.length === 0) {
      myBookingsContainer.innerHTML = '<div class="empty-state">No appointments found for this email address.</div>';
      paginationControls.classList.add('hidden');
      return;
    }

    const itemsHtml = bookings
      .map(
        (b) => `
      <div class="booking-item-card" id="booking-${b.id}">
        <div class="booking-info-group">
          <div><strong class="code-font">${escapeHtml(b.id)}</strong> • Slot: <code>${escapeHtml(b.slot_id)}</code></div>
          <div class="text-muted" style="font-size: 13px;">Patient: ${escapeHtml(b.name)} (${escapeHtml(b.email)})</div>
          <div class="text-muted" style="font-size: 13px;">Booked on: ${formatDateTime(b.created_at)}</div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="status-badge ${b.status === 'confirmed' ? 'status-confirmed' : 'status-cancelled'}">
            ${b.status === 'confirmed' ? '✓ Confirmed' : 'Cancelled'}
          </span>
          ${
            b.status === 'confirmed'
              ? `<button class="btn btn-danger" style="padding: 6px 12px; font-size: 13px;" onclick="cancelBooking('${b.id}')">Cancel</button>`
              : ''
          }
        </div>
      </div>
    `
      )
      .join('');

    if (isAppend) {
      myBookingsContainer.insertAdjacentHTML('beforeend', itemsHtml);
    } else {
      myBookingsContainer.innerHTML = itemsHtml;
    }

    if (myBookingsCursor) {
      paginationControls.classList.remove('hidden');
    } else {
      paginationControls.classList.add('hidden');
    }
  } catch (err) {
    if (!isAppend) {
      myBookingsContainer.innerHTML = `<div class="empty-state" style="color: var(--danger);">Error: ${escapeHtml(err.message)}</div>`;
    } else {
      showToast(err.message, 'error');
    }
  }
}

// Cancel Booking (Level 3)
window.cancelBooking = async function (bookingId) {
  if (!confirm('Are you sure you want to cancel this appointment? This will free the slot.')) {
    return;
  }

  try {
    await apiFetch(`/bookings/${bookingId}`, {
      method: 'DELETE',
    });

    showToast('Appointment cancelled successfully (Level 3 verified).');
    fetchMyBookings(false);
    loadSlots();
  } catch (err) {
    showToast(`Cancellation failed: ${err.message}`, 'error');
  }
};

// API Key Modal Controls
btnToggleKey.addEventListener('click', () => {
  inputApiKey.value = currentApiKey;
  keyModal.classList.remove('hidden');
});

btnCloseKeyModal.addEventListener('click', () => keyModal.classList.add('hidden'));

btnSaveKey.addEventListener('click', () => {
  const newKey = inputApiKey.value.trim();
  if (newKey) {
    currentApiKey = newKey;
    sessionStorage.setItem('X_API_KEY', newKey);
    keyModal.classList.add('hidden');
    showToast('API Key updated.');
    loadSlots();
  }
});

btnCloseBookingModal.addEventListener('click', closeBookingModal);
btnCancelModal.addEventListener('click', closeBookingModal);

// Initial Load
loadSlots();

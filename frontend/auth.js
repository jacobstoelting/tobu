// auth.js — Credential management for Tobu
// Stores Garmin + Anthropic credentials in localStorage and passes them as headers.

function getHeaders() {
    return {
        'X-Garmin-Email': localStorage.getItem('garmin_email') || '',
        'X-Garmin-Password': localStorage.getItem('garmin_password') || '',
        'X-Anthropic-Key': localStorage.getItem('anthropic_key') || '',
    };
}

function hasCredentials() {
    return !!(
        localStorage.getItem('garmin_email') &&
        localStorage.getItem('garmin_password') &&
        localStorage.getItem('anthropic_key')
    );
}

function saveCredentials(email, password, apiKey) {
    localStorage.setItem('garmin_email', email);
    localStorage.setItem('garmin_password', password);
    localStorage.setItem('anthropic_key', apiKey);
}

function openSettingsModal() {
    document.getElementById('settings-modal').style.display = 'flex';
    document.getElementById('settings-email').value = localStorage.getItem('garmin_email') || '';
    document.getElementById('settings-password').value = localStorage.getItem('garmin_password') || '';
    document.getElementById('settings-apikey').value = localStorage.getItem('anthropic_key') || '';
    document.getElementById('settings-error').textContent = '';
}

function closeSettingsModal() {
    if (hasCredentials()) {
        document.getElementById('settings-modal').style.display = 'none';
    }
}

function submitSettings() {
    const email = document.getElementById('settings-email').value.trim();
    const password = document.getElementById('settings-password').value.trim();
    const apiKey = document.getElementById('settings-apikey').value.trim();
    const errorEl = document.getElementById('settings-error');

    if (!email || !password || !apiKey) {
        errorEl.textContent = 'All fields are required.';
        return;
    }

    saveCredentials(email, password, apiKey);
    document.getElementById('settings-modal').style.display = 'none';
    window.location.reload();
}

function injectSettingsModal() {
    // Add settings button to nav
    const nav = document.querySelector('nav');
    if (nav) {
        const btn = document.createElement('button');
        btn.className = 'btn-settings';
        btn.textContent = '⚙';
        btn.title = 'Settings';
        btn.onclick = openSettingsModal;
        nav.appendChild(btn);
    }

    // Inject modal HTML
    const modal = document.createElement('div');
    modal.id = 'settings-modal';
    modal.className = 'settings-modal-overlay';
    modal.innerHTML = `
        <div class="settings-modal">
            <div class="settings-title">Settings</div>
            <p class="settings-desc">Enter your credentials to use Tobu. These are stored only in your browser.</p>
            <label class="settings-label">Garmin Email</label>
            <input class="settings-input" id="settings-email" type="email" placeholder="you@example.com" autocomplete="username" />
            <label class="settings-label">Garmin Password</label>
            <input class="settings-input" id="settings-password" type="password" placeholder="Your Garmin password" autocomplete="current-password" />
            <label class="settings-label">Anthropic API Key</label>
            <input class="settings-input" id="settings-apikey" type="password" placeholder="sk-ant-..." autocomplete="off" />
            <div id="settings-error" class="settings-error"></div>
            <div class="settings-actions">
                <button class="btn-settings-cancel" onclick="closeSettingsModal()">Cancel</button>
                <button class="btn-settings-save" onclick="submitSettings()">Save</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function initAuth() {
    injectSettingsModal();
    if (!hasCredentials()) {
        openSettingsModal();
    }
}

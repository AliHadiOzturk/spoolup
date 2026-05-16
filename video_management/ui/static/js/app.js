// Video Management System - Main App

class VideoManagementApp {
    constructor() {
        this.apiBaseUrl = '';
        this.token = localStorage.getItem('access_token');
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.checkAuth();
    }

    setupEventListeners() {
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.handleLogout());
        }
    }

    checkAuth() {
        if (!this.token && !window.location.pathname.includes('/login')) {
            window.location.href = '/login';
        }
    }

    async handleLogin(e) {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        try {
            const response = await fetch('/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username, password }),
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('access_token', data.access_token);
                window.location.href = '/dashboard';
            } else {
                const error = await response.json();
                this.showAlert(error.detail || 'Login failed', 'error');
                this.showToast(error.detail || 'Login failed', 'error');
            }
        } catch (err) {
            this.showAlert('Network error', 'error');
            this.showToast('Network error', 'error');
        }
    }

    handleLogout() {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
    }

    async apiRequest(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                this.handleLogout();
                return null;
            }

            if (!response.ok) {
                let errorMessage = `Request failed: ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorData.message || errorMessage;
                } catch (_) {
                    // response body wasn't JSON
                }
                this.showToast(errorMessage, 'error');
            }

            return response;
        } catch (err) {
            this.showToast('Network error: ' + (err.message || 'Unable to connect'), 'error');
            throw err;
        }
    }

    showAlert(message, type = 'error') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;

        const container = document.querySelector('.container') || document.body;
        container.insertBefore(alertDiv, container.firstChild);

        setTimeout(() => alertDiv.remove(), 5000);
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        const colors = {
            success: 'rgba(16, 185, 129, 0.95)',
            error: 'rgba(239, 68, 68, 0.95)',
            warning: 'rgba(245, 158, 11, 0.95)',
            info: 'rgba(59, 130, 246, 0.95)',
        };
        const color = colors[type] || colors.info;

        toast.style.cssText = `
            background: ${color};
            color: white;
            padding: 0.875rem 1.25rem;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.875rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
            pointer-events: auto;
            animation: fadeIn 0.2s ease-out;
            max-width: 400px;
        `;
        toast.textContent = message;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'fadeOut 0.2s ease-out';
            toast.addEventListener('animationend', () => toast.remove());
            setTimeout(() => toast.remove(), 250);
        }, 4000);
    }

    formatDate(dateString) {
        return new Date(dateString).toLocaleString();
    }

    formatFileSize(bytes) {
        if (bytes === 0 || bytes === null || bytes === undefined) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    formatDuration(seconds) {
        if (!seconds || seconds <= 0) return '0s';
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        if (hours > 0) {
            return `${hours}h ${mins}m`;
        }
        if (mins > 0) {
            return `${mins}m ${secs}s`;
        }
        return `${secs}s`;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VideoManagementApp();
});

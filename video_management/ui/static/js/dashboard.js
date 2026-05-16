// Video Management System - Dashboard

class DashboardManager {
    constructor() {
        this.printers = [];
        this.init();
    }

    async init() {
        await Promise.all([
            this.loadPrinters(),
            this.loadDashboardData(),
        ]);
    }

    async loadPrinters() {
        try {
            const response = await window.app.apiRequest('/api/printers/');
            if (!response) return;
            this.printers = await response.json();
        } catch (err) {
            console.error('Failed to load printers:', err);
        }
    }

    async loadDashboardData() {
        try {
            const [analyticsResponse, uploadsResponse] = await Promise.all([
                window.app.apiRequest('/api/analytics/'),
                window.app.apiRequest('/api/uploads/'),
            ]);

            let analytics = { total_videos: 0, pending_uploads: 0, published_videos: 0, total_views: 0 };
            let uploads = [];

            if (analyticsResponse && analyticsResponse.ok) {
                analytics = await analyticsResponse.json();
            }

            if (uploadsResponse && uploadsResponse.ok) {
                uploads = await uploadsResponse.json();
            }

            this.renderStats(analytics);
            this.renderRecentActivity(uploads);
            this.renderPlatformStatus(analytics.platform_status || {});
        } catch (err) {
            console.error('Failed to load dashboard:', err);
        }
    }

    renderStats(data) {
        document.getElementById('stat-total-videos').textContent = (data.total_videos || 0).toLocaleString();
        document.getElementById('stat-pending-uploads').textContent = (data.pending_uploads || 0).toLocaleString();
        document.getElementById('stat-published').textContent = (data.published_videos || 0).toLocaleString();
        document.getElementById('stat-total-views').textContent = (data.total_views || 0).toLocaleString();
    }

    renderRecentActivity(uploads) {
        const container = document.getElementById('recent-activity');
        if (!container) return;

        const sorted = uploads
            .sort((a, b) => new Date(b.created_at || b.uploaded_at || 0) - new Date(a.created_at || a.uploaded_at || 0))
            .slice(0, 5);

        if (sorted.length === 0) {
            container.innerHTML = '<p class="text-secondary" style="color: var(--text-secondary);">No recent activity</p>';
            return;
        }

        container.innerHTML = sorted.map(upload => {
            const icon = upload.platform === 'youtube' ? '📺' : upload.platform === 'tiktok' ? '🎵' : '📤';
            const statusColor = upload.status === 'completed' || upload.status === 'published' ? 'var(--success-color)' :
                                upload.status === 'failed' || upload.status === 'error' ? 'var(--error-color)' :
                                'var(--warning-color)';
            const time = upload.uploaded_at || upload.created_at ? window.app.formatDate(upload.uploaded_at || upload.created_at) : 'Pending';

            return `
                <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--background); border-radius: 8px; margin-bottom: 0.5rem;">
                    <div style="font-size: 1.5rem;">${icon}</div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; font-size: 0.875rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            ${upload.title || 'Untitled'}
                        </div>
                        <div style="display: flex; gap: 0.5rem; align-items: center; margin-top: 0.125rem;">
                            <span style="font-size: 0.75rem; color: ${statusColor}; font-weight: 600;">${upload.status || 'Unknown'}</span>
                            <span style="font-size: 0.75rem; color: var(--text-secondary);">• ${upload.platform || 'Unknown'}</span>
                        </div>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-secondary); white-space: nowrap;">${time}</div>
                </div>
            `;
        }).join('');
    }

    renderPlatformStatus(status) {
        const container = document.getElementById('platform-status');
        if (!container) return;

        const platforms = [
            { key: 'youtube', name: 'YouTube', icon: '📺' },
            { key: 'tiktok', name: 'TikTok', icon: '🎵' },
        ];

        container.innerHTML = platforms.map(p => {
            const data = status[p.key] || { connected: false };
            const connected = data.connected;
            const statusText = connected ? 'Connected' : 'Disconnected';
            const statusColor = connected ? 'var(--success-color)' : 'var(--error-color)';
            const statusBg = connected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';

            return `
                <div style="display: flex; align-items: center; gap: 0.75rem; padding: 1rem; background: var(--background); border-radius: 8px; margin-bottom: 0.5rem;">
                    <div style="font-size: 1.75rem;">${p.icon}</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 600; font-size: 0.9375rem;">${p.name}</div>
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.25rem;">
                            <span style="width: 8px; height: 8px; border-radius: 50%; background: ${statusColor}; display: inline-block;"></span>
                            <span style="font-size: 0.8125rem; color: var(--text-secondary);">${statusText}</span>
                        </div>
                        ${data.quota_used !== undefined ? `
                            <div style="margin-top: 0.5rem;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 0.125rem;">
                                    <span style="font-size: 0.6875rem; color: var(--text-secondary);">Quota</span>
                                    <span style="font-size: 0.6875rem; color: var(--text-secondary);">${data.quota_used}% used</span>
                                </div>
                                <div style="width: 100%; height: 4px; background: var(--surface-hover); border-radius: 2px; overflow: hidden;">
                                    <div style="width: ${data.quota_used}%; height: 100%; background: ${data.quota_used > 90 ? 'var(--error-color)' : data.quota_used > 70 ? 'var(--warning-color)' : 'var(--success-color)'}; border-radius: 2px;"></div>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    async syncFromPrinter() {
        const btn = document.getElementById('sync-from-printer-btn');
        if (!btn) return;

        if (this.printers.length === 0) {
            window.app.showToast('No printers configured', 'error');
            return;
        }

        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span>Syncing...</span>';

        try {
            const printer = this.printers[0];
            const response = await window.app.apiRequest(`/api/printers/${printer.id}/sync`, {
                method: 'POST'
            });

            if (!response) {
                btn.disabled = false;
                btn.innerHTML = originalText;
                return;
            }

            if (response.ok) {
                const result = await response.json();
                window.app.showToast(
                    `Sync completed: ${result.synced_videos || 0} new video(s) found`,
                    'success'
                );
                this.loadDashboardData();
            } else {
                const error = await response.json();
                window.app.showToast(error.detail || 'Sync failed', 'error');
            }
        } catch (err) {
            window.app.showToast('Sync failed: ' + (err.message || 'Unknown error'), 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
}

let dashboardManager;
document.addEventListener('DOMContentLoaded', () => {
    dashboardManager = new DashboardManager();
});

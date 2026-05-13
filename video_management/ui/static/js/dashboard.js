// Video Management System - Dashboard

class DashboardManager {
    constructor() {
        this.init();
    }

    async init() {
        await this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            const response = await window.app.apiRequest('/api/analytics');
            if (!response) return;

            const data = await response.json();
            this.renderStats(data);
            this.renderRecentUploads(data.recent_uploads);
            this.renderPlatformBreakdown(data.platform_breakdown);
        } catch (err) {
            console.error('Failed to load dashboard:', err);
        }
    }

    renderStats(data) {
        const statsContainer = document.getElementById('stats-container');
        if (!statsContainer) return;

        const stats = [
            { label: 'Total Uploads', value: data.total_uploads, icon: 'upload' },
            { label: 'Total Views', value: data.total_views, icon: 'eye' },
            { label: 'Total Likes', value: data.total_likes, icon: 'heart' },
            { label: 'Comments', value: data.total_comments, icon: 'message' },
        ];

        statsContainer.innerHTML = stats.map(stat => `
            <div class="card">
                <div class="stat-value">${stat.value.toLocaleString()}</div>
                <div class="stat-label">${stat.label}</div>
            </div>
        `).join('');
    }

    renderRecentUploads(uploads) {
        const container = document.getElementById('recent-uploads');
        if (!container) return;

        if (uploads.length === 0) {
            container.innerHTML = '<p class="text-secondary">No uploads yet</p>';
            return;
        }

        container.innerHTML = `
            <table class="table">
                <thead>
                    <tr>
                        <th>Platform</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
                    ${uploads.map(upload => `
                        <tr>
                            <td>${upload.platform}</td>
                            <td>${upload.title || 'Untitled'}</td>
                            <td><span class="badge badge-${upload.status === 'completed' ? 'success' : 'warning'}">${upload.status}</span></td>
                            <td>${upload.uploaded_at ? window.app.formatDate(upload.uploaded_at) : 'Pending'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    renderPlatformBreakdown(breakdown) {
        const container = document.getElementById('platform-breakdown');
        if (!container) return;

        const platforms = Object.entries(breakdown);
        if (platforms.length === 0) {
            container.innerHTML = '<p class="text-secondary">No data available</p>';
            return;
        }

        container.innerHTML = platforms.map(([platform, stats]) => `
            <div class="card">
                <h3>${platform.charAt(0).toUpperCase() + platform.slice(1)}</h3>
                <div class="platform-stats">
                    <div>Uploads: ${stats.uploads}</div>
                    <div>Views: ${stats.views}</div>
                    <div>Likes: ${stats.likes}</div>
                </div>
            </div>
        `).join('');
    }
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('dashboard-page')) {
        new DashboardManager();
    }
});

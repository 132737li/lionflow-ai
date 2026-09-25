/* ==========================================
   LionFlow AI — JavaScript principal
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {
    // Sidebar toggle mobile
    const toggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => sidebar.classList.toggle('show'));
    }

    // Auto-dismiss des alertes après 6s
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
        setTimeout(() => {
            try { bootstrap.Alert.getOrCreateInstance(alert).close(); } catch(e) {}
        }, 6000);
    });

    // Confirmation pour les actions dangereuses
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', (e) => {
            if (!confirm(el.dataset.confirm)) e.preventDefault();
        });
    });
});
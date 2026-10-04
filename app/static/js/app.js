/* ==========================================
   LionFlow AI — JavaScript principal
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {

    // ============================================
    // SIDEBAR MOBILE
    // ============================================
    const toggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const pageContent = document.getElementById('page-content-wrapper');

    if (toggle && sidebar) {
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            sidebar.classList.toggle('show');
        });

        if (pageContent) {
            pageContent.addEventListener('click', () => {
                if (sidebar.classList.contains('show') && window.innerWidth < 992) {
                    sidebar.classList.remove('show');
                }
            });
        }

        document.addEventListener('click', (e) => {
            if (
                sidebar.classList.contains('show') &&
                !sidebar.contains(e.target) &&
                !toggle.contains(e.target) &&
                window.innerWidth < 992
            ) {
                sidebar.classList.remove('show');
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && sidebar.classList.contains('show')) {
                sidebar.classList.remove('show');
            }
        });

        sidebar.querySelectorAll('.lf-nav-link').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) {
                    sidebar.classList.remove('show');
                }
            });
        });
    }

    // ============================================
    // TABLES RESPONSIVE
    // ============================================
    function transformTablesForMobile() {
        document.querySelectorAll('.table-responsive table').forEach(table => {
            const headers = [];
            table.querySelectorAll('thead th').forEach(th => {
                headers.push(th.textContent.trim());
            });
            if (headers.length === 0) return;
            table.querySelectorAll('tbody tr').forEach(tr => {
                tr.querySelectorAll('td').forEach((td, index) => {
                    if (headers[index]) {
                        td.setAttribute('data-label', headers[index]);
                    }
                });
            });
        });
    }

    transformTablesForMobile();

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(transformTablesForMobile, 250);
    });

    // ============================================
    // ALERTES AUTO-DISMISS
    // ============================================
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
        setTimeout(() => {
            try {
                bootstrap.Alert.getOrCreateInstance(alert).close();
            } catch(e) {}
        }, 6000);
    });

    // ============================================
    // CONFIRMATION
    // ============================================
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', (e) => {
            if (!confirm(el.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // ============================================
    // FERMER LES MODALES AVEC ÉCHAP
    // ============================================
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.show').forEach(modal => {
                try {
                    bootstrap.Modal.getInstance(modal)?.hide();
                } catch(err) {}
            });
        }
    });

});

// ============================================
// GESTION DES THÈMES — Hors du DOMContentLoaded
// pour garantir qu'elle s'exécute après
// ============================================
(function() {
    const THEMES = ['light', 'dark', 'purple', 'orange', 'blue'];
    const DEFAULT_THEME = 'light';
    const STORAGE_KEY = 'lionflow_theme';

    function getCurrentTheme() {
        return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    }

    function applyTheme(theme) {
        if (!THEMES.includes(theme)) theme = DEFAULT_THEME;

        // Appliquer sur <html>
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(STORAGE_KEY, theme);

        // Mettre à jour l'état actif
        document.querySelectorAll('.theme-option').forEach(opt => {
            opt.classList.toggle('active', opt.dataset.theme === theme);
        });

        console.log('[Thème] Appliqué :', theme);
    }

    // Appliquer le thème sauvegardé au plus tôt
    applyTheme(getCurrentTheme());

    // Gérer les clics sur les options de thème (délégation globale)
    document.addEventListener('click', function(e) {
        const option = e.target.closest('.theme-option');
        if (!option) return;

        e.preventDefault();
        e.stopPropagation();

        const theme = option.dataset.theme;
        if (theme) {
            applyTheme(theme);

            // Fermer le dropdown
            const dropdown = option.closest('.dropdown-menu');
            if (dropdown) {
                try {
                    const toggle = dropdown.previousElementSibling;
                    const bsDropdown = bootstrap.Dropdown.getInstance(toggle);
                    if (bsDropdown) bsDropdown.hide();
                } catch(err) {}
            }
        }
    }, true); // ← capture: true pour intercepter AVANT Bootstrap

    // Reappliquer après le chargement complet
    window.addEventListener('load', () => applyTheme(getCurrentTheme()));

})();
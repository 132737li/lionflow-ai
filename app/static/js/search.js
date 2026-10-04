/* ==========================================
   LionFlow AI — Recherche globale (Ctrl+K)
   Avec gestion du bouton "retour" Android
   ========================================== */
(function() {
    'use strict';

    let searchModal = null;
    let searchInput = null;
    let resultsContainer = null;
    let currentResults = [];
    let selectedIndex = 0;
    let debounceTimer = null;
    let isModalOpen = false;

    // ==========================================
    // INITIALISATION
    // ==========================================
    function init() {
        const trigger = document.getElementById('lfSearchTrigger');
        const modalEl = document.getElementById('lfSearchModal');
        if (!modalEl) return;

        searchModal = new bootstrap.Modal(modalEl);
        searchInput = document.getElementById('lfSearchInput');
        resultsContainer = document.getElementById('lfSearchResults');

        // ⚠️ Empêcher l'autocomplétion Chrome/Safari
        if (searchInput) {
            searchInput.setAttribute('autocomplete', 'off');
            searchInput.setAttribute('autocorrect', 'off');
            searchInput.setAttribute('autocapitalize', 'off');
            searchInput.setAttribute('spellcheck', 'false');
            searchInput.setAttribute('name', 'lf_search_field');
            searchInput.setAttribute('readonly', 'readonly');
            setTimeout(() => searchInput.removeAttribute('readonly'), 100);
            searchInput.addEventListener('focus', () => {
                searchInput.removeAttribute('readonly');
            });
        }

        // Bouton dans la topbar
        if (trigger) {
            trigger.addEventListener('click', openSearch);
        }

        // Raccourci Ctrl+K (ou Cmd+K sur Mac)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                openSearch();
            }
        });

        // ⚠️ Intercepter le bouton "retour" Android quand le modal est ouvert
        window.addEventListener('popstate', (e) => {
            if (isModalOpen) {
                // Empêcher la navigation → fermer le modal
                e.preventDefault();
                searchModal.hide();
                return;
            }
        });

        // À l'ouverture : pousser un état dans l'historique
        modalEl.addEventListener('show.bs.modal', () => {
            isModalOpen = true;
            // Ajouter un état pour capturer le "retour"
            try {
                history.pushState({ lfModal: 'search' }, '', location.href);
            } catch (e) {
                // Ignore
            }
        });

        // À l'ouverture complète
        modalEl.addEventListener('shown.bs.modal', () => {
            searchInput.removeAttribute('readonly');
            searchInput.focus();
            searchInput.select();
        });

        // À la fermeture
        modalEl.addEventListener('hidden.bs.modal', () => {
            isModalOpen = false;
            searchInput.value = '';
            resultsContainer.innerHTML = renderEmpty();
            currentResults = [];
            selectedIndex = 0;

            // Si on a poussé un état et qu'on ferme "normalement",
            // on retire l'état pour ne pas "bloquer" l'historique
            if (history.state && history.state.lfModal === 'search') {
                try {
                    history.back();
                } catch (e) {
                    // Ignore
                }
            }
        });

        // Input de recherche
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            const q = e.target.value.trim();
            if (q.length < 2) {
                resultsContainer.innerHTML = renderEmpty();
                currentResults = [];
                return;
            }
            debounceTimer = setTimeout(() => doSearch(q), 200);
        });

        // Navigation clavier
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                moveSelection(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                moveSelection(-1);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                const selected = currentResults[selectedIndex];
                if (selected && selected.url) {
                    // Nettoyer l'historique avant de naviguer
                    isModalOpen = false;
                    window.location.href = selected.url;
                }
            }
        });
    }

    function openSearch() {
        if (!searchModal) return;
        searchModal.show();
    }

    // ==========================================
    // RECHERCHE API
    // ==========================================
    async function doSearch(query) {
        try {
            const res = await fetch(`/search/?q=${encodeURIComponent(query)}`, {
                credentials: 'same-origin',
            });
            const data = await res.json();
            if (data.success) {
                renderResults(data.results);
            }
        } catch (err) {
            console.error('[Search] Erreur:', err);
        }
    }

    // ==========================================
    // RENDU
    // ==========================================
    function renderEmpty() {
        return `
            <div class="lf-search-empty">
                <i class="bi bi-search"></i>
                <p>Tapez au moins 2 caractères pour rechercher.</p>
            </div>
        `;
    }

    function renderNoResults() {
        return `
            <div class="lf-search-empty">
                <i class="bi bi-inbox"></i>
                <p>Aucun résultat trouvé.</p>
            </div>
        `;
    }

    function renderResults(results) {
        currentResults = [];
        selectedIndex = 0;

        const groups = [
            { key: 'contacts', label: '👥 Contacts' },
            { key: 'campaigns', label: '📢 Campagnes' },
            { key: 'templates', label: '📝 Modèles' },
            { key: 'messages', label: '💬 Messages' },
            { key: 'conversations', label: '🤖 Chatbot' },
        ];

        let html = '';
        let totalShown = 0;

        for (const group of groups) {
            const items = results[group.key] || [];
            if (items.length === 0) continue;

            html += `<div class="lf-search-group">`;
            html += `<div class="lf-search-group-title">${group.label}</div>`;

            for (const item of items) {
                const idx = currentResults.length;
                currentResults.push(item);
                totalShown++;

                html += `
                    <a href="${item.url}" class="lf-search-item" data-index="${idx}">
                        <div class="lf-search-item-icon">
                            <i class="bi ${item.icon}"></i>
                        </div>
                        <div class="lf-search-item-content">
                            <div class="lf-search-item-title">${escapeHtml(item.title || '')}</div>
                            <div class="lf-search-item-subtitle">${escapeHtml(item.subtitle || '')}</div>
                        </div>
                    </a>
                `;
            }
            html += `</div>`;
        }

        if (totalShown === 0) {
            html = renderNoResults();
        }

        resultsContainer.innerHTML = html;

        document.querySelectorAll('.lf-search-item').forEach(el => {
            el.addEventListener('mouseenter', () => {
                selectedIndex = parseInt(el.dataset.index);
                updateSelection();
            });
        });

        updateSelection();
    }

    function updateSelection() {
        document.querySelectorAll('.lf-search-item').forEach(el => {
            const idx = parseInt(el.dataset.index);
            el.classList.toggle('selected', idx === selectedIndex);
        });
    }

    function moveSelection(direction) {
        if (currentResults.length === 0) return;
        selectedIndex += direction;
        if (selectedIndex < 0) selectedIndex = currentResults.length - 1;
        if (selectedIndex >= currentResults.length) selectedIndex = 0;
        updateSelection();
        const selected = document.querySelector(`.lf-search-item[data-index="${selectedIndex}"]`);
        if (selected) selected.scrollIntoView({ block: 'nearest' });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ==========================================
    // DÉMARRAGE
    // ==========================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
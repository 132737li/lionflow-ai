/* ==========================================
   LionFlow AI — Notifications Push PWA
   ========================================== */

(function() {
    'use strict';

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.log('[Push] Non supporté par ce navigateur');
        return;
    }

    // ==========================================
    // UTILITAIRES
    // ==========================================
    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    async function getVapidKey() {
        const res = await fetch('/push/vapid-public-key', {
            credentials: 'same-origin',
        });
        const data = await res.json();
        return data.public_key;
    }

    async function getSubscription() {
        const reg = await navigator.serviceWorker.ready;
        return reg.pushManager.getSubscription();
    }

    // ==========================================
    // ABONNEMENT
    // ==========================================
    async function subscribe() {
        try {
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                console.log('[Push] Permission refusée');
                return null;
            }

            const vapidKey = await getVapidKey();
            if (!vapidKey) {
                console.error('[Push] Clé VAPID manquante');
                return null;
            }

            const reg = await navigator.serviceWorker.ready;
            const sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(vapidKey),
            });

            // Envoyer au serveur
            const res = await fetch('/push/subscribe', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(sub.toJSON()),
            });

            const data = await res.json();
            if (data.success) {
                console.log('[Push] Abonnement enregistré');
                updateUI(true);
            }
            return sub;
        } catch (err) {
            console.error('[Push] Erreur abonnement:', err);
            return null;
        }
    }

    async function unsubscribe() {
        try {
            const sub = await getSubscription();
            if (!sub) return;

            await fetch('/push/unsubscribe', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ endpoint: sub.endpoint }),
            });

            await sub.unsubscribe();
            console.log('[Push] Désabonné');
            updateUI(false);
        } catch (err) {
            console.error('[Push] Erreur désabonnement:', err);
        }
    }

    function getCsrfToken() {
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }

    // ==========================================
    // UI
    // ==========================================
    function updateUI(subscribed) {
        const btn = document.getElementById('pushToggleBtn');
        if (!btn) return;
        if (subscribed) {
            btn.classList.remove('btn-outline-primary');
            btn.classList.add('btn-success');
            btn.innerHTML = '<i class="bi bi-bell-fill"></i> Notifications activées';
        } else {
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-primary');
            btn.innerHTML = '<i class="bi bi-bell"></i> Activer les notifications';
        }
    }

    async function initUI() {
        const btn = document.getElementById('pushToggleBtn');
        if (!btn) return;

        // Vérifier l'état actuel
        try {
            const sub = await getSubscription();
            updateUI(!!sub);
        } catch (e) {
            updateUI(false);
        }

        // Toggle au clic
        btn.addEventListener('click', async () => {
            const sub = await getSubscription();
            if (sub) {
                await unsubscribe();
            } else {
                await subscribe();
            }
        });

        // Bouton de test
        const testBtn = document.getElementById('pushTestBtn');
        if (testBtn) {
            testBtn.addEventListener('click', async () => {
                try {
                    const res = await fetch('/push/test', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'X-CSRFToken': getCsrfToken(),
                        },
                    });
                    const data = await res.json();
                    alert(data.message || 'Test envoyé');
                } catch (e) {
                    alert('Erreur : ' + e.message);
                }
            });
        }
    }

    // Exposer pour usage externe
    window.LionFlowPush = {
        subscribe,
        unsubscribe,
        isSubscribed: async () => !!(await getSubscription()),
    };

    // Init au chargement
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }

})();
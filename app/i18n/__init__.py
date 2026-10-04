"""
Service de traduction (i18n).
Système léger basé sur des dictionnaires Python.
"""
from flask import session, current_app
from flask_login import current_user

from app.i18n.locales.fr import TRANSLATIONS as FR
from app.i18n.locales.en import TRANSLATIONS as EN
from app.i18n.locales.rn import TRANSLATIONS as RN
from app.i18n.locales.sw import TRANSLATIONS as SW
from app.i18n.locales.es import TRANSLATIONS as ES
from app.i18n.locales.pt import TRANSLATIONS as PT  # bonus
from app.i18n.locales.ar import TRANSLATIONS as AR  # bonus


# Langues disponibles
LANGUAGES = {
    "fr": {"name": "Français",   "flag": "🇫🇷"},
    "en": {"name": "English",    "flag": "🇬🇧"},
    "rn": {"name": "Kirundi",    "flag": "🇧🇮"},
    "sw": {"name": "Kiswahili",  "flag": "🇹🇿"},
    "es": {"name": "Español",    "flag": "🇪🇸"},
    "pt": {"name": "Português",  "flag": "🇵🇹"},   # bonus
    "ar": {"name": "العربية",     "flag": "🇸🇦"},   # bonus
}

DEFAULT_LANGUAGE = "fr"

# Registre des traductions
TRANSLATIONS_MAP = {
    "fr": FR,
    "en": EN,
    "rn": RN,
    "sw": SW,
    "es": ES,
    "pt": PT,
    "ar": AR,
}


# ==================================================
# SERVICE
# ==================================================
class I18nService:

    @staticmethod
    def get_current_language() -> str:
        """Détermine la langue active."""
        # 1. Session (préférence temporaire)
        lang = session.get("language")
        if lang and lang in LANGUAGES:
            return lang

        # 2. Utilisateur connecté
        if current_user.is_authenticated and getattr(current_user, "language", None):
            user_lang = current_user.language
            if user_lang in LANGUAGES:
                session["language"] = user_lang
                return user_lang

        # 3. Accept-Language du navigateur
        from flask import request
        browser_lang = request.accept_languages.best_match(list(LANGUAGES.keys()))
        if browser_lang:
            return browser_lang

        return DEFAULT_LANGUAGE

    @staticmethod
    def set_language(lang: str) -> bool:
        """Change la langue active."""
        if lang not in LANGUAGES:
            return False

        session["language"] = lang

        # Sauvegarder sur l'utilisateur connecté
        if current_user.is_authenticated:
            current_user.language = lang
            from app.extensions import db
            db.session.commit()

        return True

    @staticmethod
    def t(key: str, default: str = None, **kwargs) -> str:
        """
        Traduit une clé.
        - Si la traduction existe dans la langue active → utilise
        - Sinon → fallback sur français
        - Sinon → utilise `default` ou la clé brute
        """
        lang = I18nService.get_current_language()
        translations = TRANSLATIONS_MAP.get(lang, FR)
        fallback = TRANSLATIONS_MAP.get(DEFAULT_LANGUAGE, {})

        text = translations.get(key) or fallback.get(key) or default or key

        # Support des variables : t('hello', name='Jean')
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError):
                pass

        return text


# ==================================================
# HELPER GLOBAL POUR LES TEMPLATES
# ==================================================
def t(key: str, default: str = None, **kwargs) -> str:
    """Fonction de traduction exposée aux templates."""
    return I18nService.t(key, default=default, **kwargs)
"""
Minimal UI translation layer - two supported languages, no i18n framework.

Only site chrome (labels, buttons, messages) is translated here. Catalog
content (titles, descriptions, publisher/genre/series names) is curated
data and is never translated - there's no bilingual data model for that.

Language selection is server-side and stateless: resolve_language() checks
an explicit `?lang=` query param first, then falls back to the browser's
Accept-Language header. There's no cookie/session, so templates must
propagate `lang` through their own links (see base.html) to keep the choice
across navigation within a visit.
"""

from __future__ import annotations

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        "tagline": "Kinder-Hörspiele finden - abspielen auf YouTube Music",
        "meta_description": "Kostenlose, werbefreie Suche für Kinder-Hörspiele und Hörbücher auf YouTube Music.",
        "principles": (
            "Kostenlos, werbefrei und ohne Anmeldung oder Tracking. StorytimeFinder "
            "speichert oder streamt selbst keine Audiodateien - jeder Titel spielt "
            "direkt auf YouTube Music ab."
        ),
        "search_placeholder": 'Titel suchen, z.B. "König der Löwen"',
        "filter_age": "Alter:",
        "filter_series": "Reihe:",
        "filter_language": "Sprache:",
        "filter_duration": "Dauer:",
        "filter_genre": "Genre:",
        "filter_publisher": "Verlag:",
        "filter_release": "Veröffentlicht:",
        "chip_all": "Alle",
        "age_suffix": "Jahre",
        "decade_suffix": "er",
        "advanced_toggle": "Erweiterte Filter",
        "results_count_one": "{n} Hörspiel",
        "results_count_other": "{n} Hörspiele",
        "empty_filtered": "Keine Hörspiele passen zu dieser Auswahl.",
        "empty_catalog": "Der Katalog ist noch leer - führe den Refresh-Job aus, um Inhalte hinzuzufügen.",
        "episode": "Folge {n}",
        "card_publisher": "Verlag",
        "card_released": "Veröffentlicht",
        "card_play": "Auf YouTube Music abspielen",
        "footer_attribution": (
            "Alle Inhalte werden von YouTube bereitgestellt. StorytimeFinder hostet "
            "keine Audiodateien - jeder Titel verlinkt direkt zu YouTube Music."
        ),
        "footer_impressum": "Impressum",
        "footer_updated": "Katalog aktualisiert:",
        "theme_toggle": "Farbschema umschalten",
        "back_to_categories": "Alle Kategorien",
        "category_empty": "Noch keine Hörspiele in dieser Kategorie.",
        "impressum_title": "Impressum",
        "impressum_language_note": "Dieses Impressum ist gesetzlich vorgeschrieben (§5 TMG) und wird auf Deutsch bereitgestellt.",
        "duration_under30": "< 30 Min",
        "duration_30to60": "30-60 Min",
        "duration_1to2h": "1-2 Std",
        "duration_over2h": "> 2 Std",
        "category_hoerspiel": "Hörspiel",
        "category_disney": "Disney",
        "category_classic": "Klassiker",
        "language_de": "Deutsch",
        "language_en": "Englisch",
    },
    "en": {
        "tagline": "Find children's audiobooks - play them on YouTube Music",
        "meta_description": "Free, ad-free search for children's audiobooks on YouTube Music.",
        "principles": (
            "Free, ad-free, no account or tracking required. StorytimeFinder never "
            "stores or streams any audio itself - every title plays directly on "
            "YouTube Music."
        ),
        "search_placeholder": 'Search titles, e.g. "The Lion King"',
        "filter_age": "Age:",
        "filter_series": "Series:",
        "filter_language": "Language:",
        "filter_duration": "Duration:",
        "filter_genre": "Genre:",
        "filter_publisher": "Publisher:",
        "filter_release": "Released:",
        "chip_all": "All",
        "age_suffix": "years",
        "decade_suffix": "s",
        "advanced_toggle": "Advanced filters",
        "results_count_one": "{n} audiobook",
        "results_count_other": "{n} audiobooks",
        "empty_filtered": "No audiobooks match this selection.",
        "empty_catalog": "The catalog is empty - run the refresh job to add content.",
        "episode": "Episode {n}",
        "card_publisher": "Publisher",
        "card_released": "Released",
        "card_play": "Play on YouTube Music",
        "footer_attribution": (
            "All content is provided by YouTube. StorytimeFinder does not host any "
            "audio - every title links directly to YouTube Music."
        ),
        "footer_impressum": "Legal notice",
        "footer_updated": "Catalog updated:",
        "theme_toggle": "Toggle color theme",
        "back_to_categories": "All categories",
        "category_empty": "No audiobooks in this category yet.",
        "impressum_title": "Legal notice",
        "impressum_language_note": "This legal notice is required under German law (§5 TMG) and is provided in German.",
        "duration_under30": "< 30 min",
        "duration_30to60": "30-60 min",
        "duration_1to2h": "1-2 hr",
        "duration_over2h": "> 2 hr",
        "category_hoerspiel": "Audiobook",
        "category_disney": "Disney",
        "category_classic": "Classics",
        "language_de": "German",
        "language_en": "English",
    },
}


def resolve_language(accept_languages, requested: str | None) -> str:
    if requested in SUPPORTED_LANGUAGES:
        return requested
    best = accept_languages.best_match(SUPPORTED_LANGUAGES)
    return best or DEFAULT_LANGUAGE


def translate(lang: str, key: str, **kwargs) -> str:
    strings = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE])
    text = strings.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
    return text.format(**kwargs) if kwargs else text

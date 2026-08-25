"""
Minimal UI translation layer - two supported languages, no i18n framework.

Only site chrome (labels, buttons, messages) is translated here. Catalog
content (titles, descriptions, series names) is curated data and is never
translated - there's no bilingual data model for that. The exception is
genre/franchise/language/mood/seasonal, which map through fixed
`genre_<slug>` / `franchise_<slug>` / `language_<code>` / `mood_<slug>` /
`seasonal_<slug>` translation keys, since each is a small, known, enumerable
set (see refresh/overrides.py's docstring for the canonical value lists).

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
        "search_placeholder": "Hörspiel suchen...",
        "sort_label": "Sortieren:",
        "sort_title_asc": "Titel A-Z",
        "sort_title_desc": "Titel Z-A",
        "sort_duration_asc": "Dauer ↑",
        "sort_duration_desc": "Dauer ↓",
        "sort_release_asc": "Jahr ↑",
        "sort_release_desc": "Jahr ↓",
        "filter_franchise": "Franchise:",
        "filter_age": "Alter:",
        "filter_series": "Reihe:",
        "filter_language": "Sprache:",
        "filter_duration": "Dauer:",
        "filter_genre": "Genre:",
        "filter_release": "Veröffentlicht:",
        "filter_mood": "Stimmung:",
        "filter_seasonal": "Saison:",
        "filter_awards": "Auszeichnung:",
        "awards_chip": "🏆 Preisgekrönt",
        "chip_all": "Alle",
        "decade_suffix": "er",
        "advanced_toggle": "Erweiterte Filter",
        "results_count_one": "{n} Hörspiel",
        "results_count_other": "{n} Hörspiele",
        "empty_filtered": "Keine Hörspiele passen zu dieser Auswahl.",
        "empty_catalog": "Der Katalog ist noch leer - führe den Refresh-Job aus, um Inhalte hinzuzufügen.",
        "pagination_nav_label": "Seiten",
        "pagination_prev": "Zurück",
        "pagination_next": "Weiter",
        "pagination_status": "Seite {page} von {total}",
        "card_play": "Auf YouTube Music abspielen",
        "footer_attribution": (
            "Kostenlos, werbefrei und ohne Anmeldung oder Tracking. Alle Inhalte werden "
            "von YouTube Music bereitgestellt - StorytimeFinder hostet oder streamt "
            "selbst keine Audiodateien, jeder Titel verlinkt direkt zu YouTube Music."
        ),
        "footer_impressum": "Impressum",
        "footer_updated": "Katalog aktualisiert:",
        "footer_github": "GitHub",
        "footer_suggest": "Hörspiel vorschlagen",
        "date_today": "heute",
        "date_yesterday": "gestern",
        "date_days_ago_other": "vor {n} Tagen",
        "date_weeks_ago_one": "vor {n} Woche",
        "date_weeks_ago_other": "vor {n} Wochen",
        "impressum_title": "Impressum",
        "impressum_language_note": "Dieses Impressum ist gesetzlich vorgeschrieben (§5 TMG) und wird auf Deutsch bereitgestellt.",
        "duration_under30": "< 30 Min",
        "duration_30to60": "30-60 Min",
        "duration_1to2h": "1-2 Std",
        "duration_over2h": "> 2 Std",
        "age_tag_0_3": "ab 0-3 Jahren",
        "age_tag_3_5": "ab 3-5 Jahren",
        "age_tag_6_8": "ab 6-8 Jahren",
        "age_tag_9_11": "ab 9-11 Jahren",
        "age_tag_12_plus": "ab 12 Jahren",
        "age_tag_short_0_3": "0-3 Jahre",
        "age_tag_short_3_5": "3-5 Jahre",
        "age_tag_short_6_8": "6-8 Jahre",
        "age_tag_short_9_11": "9-11 Jahre",
        "age_tag_short_12_plus": "12+ Jahre",
        "genre_fairy_tale": "Märchen",
        "genre_adventure": "Abenteuer",
        "genre_mystery": "Krimi",
        "genre_fantasy": "Fantasy",
        "genre_educational": "Wissen",
        "genre_bedtime_story": "Gute-Nacht-Geschichte",
        "genre_classic": "Klassiker",
        "genre_comedy": "Komödie",
        "franchise_disney": "Disney",
        "franchise_pixar": "Pixar",
        "franchise_dreamworks": "DreamWorks",
        "franchise_marvel": "Marvel",
        "franchise_star_wars": "Star Wars",
        "franchise_bibi_blocksberg": "Bibi Blocksberg",
        "franchise_benjamin_bluemchen": "Benjamin Blümchen",
        "franchise_die_drei_fragezeichen": "Die drei ???",
        "franchise_tkkg": "TKKG",
        "language_de": "Deutsch",
        "language_en": "Englisch",
        "mood_calm": "Ruhig",
        "mood_funny": "Lustig",
        "mood_spooky": "Gruselig",
        "mood_adventurous": "Abenteuerlich",
        "mood_heartwarming": "Herzerwärmend",
        "mood_exciting": "Spannend",
        "mood_silly": "Albern",
        "mood_gentle": "Sanft",
        "seasonal_winter": "Winter",
        "seasonal_christmas": "Weihnachten",
        "seasonal_halloween": "Halloween",
        "seasonal_easter": "Ostern",
        "seasonal_summer": "Sommer",
        "seasonal_birthday": "Geburtstag",
    },
    "en": {
        "tagline": "Find children's audiobooks - play them on YouTube Music",
        "meta_description": "Free, ad-free search for children's audiobooks on YouTube Music.",
        "search_placeholder": "Search audiobooks...",
        "sort_label": "Sort:",
        "sort_title_asc": "Title A-Z",
        "sort_title_desc": "Title Z-A",
        "sort_duration_asc": "Duration ↑",
        "sort_duration_desc": "Duration ↓",
        "sort_release_asc": "Year ↑",
        "sort_release_desc": "Year ↓",
        "filter_franchise": "Franchise:",
        "filter_age": "Age:",
        "filter_series": "Series:",
        "filter_language": "Language:",
        "filter_duration": "Duration:",
        "filter_genre": "Genre:",
        "filter_release": "Released:",
        "filter_mood": "Mood:",
        "filter_seasonal": "Season:",
        "filter_awards": "Award:",
        "awards_chip": "🏆 Award-winning",
        "chip_all": "All",
        "decade_suffix": "s",
        "advanced_toggle": "Advanced filters",
        "results_count_one": "{n} audiobook",
        "results_count_other": "{n} audiobooks",
        "empty_filtered": "No audiobooks match this selection.",
        "empty_catalog": "The catalog is empty - run the refresh job to add content.",
        "pagination_nav_label": "Pages",
        "pagination_prev": "Previous",
        "pagination_next": "Next",
        "pagination_status": "Page {page} of {total}",
        "card_play": "Play on YouTube Music",
        "footer_attribution": (
            "Free, ad-free, no account or tracking required. All content is provided "
            "by YouTube Music - StorytimeFinder never hosts or streams any audio "
            "itself, every title links directly to YouTube Music."
        ),
        "footer_impressum": "Legal notice",
        "footer_updated": "Catalog updated:",
        "footer_github": "GitHub",
        "footer_suggest": "Suggest an audiobook",
        "date_today": "today",
        "date_yesterday": "yesterday",
        "date_days_ago_other": "{n} days ago",
        "date_weeks_ago_one": "{n} week ago",
        "date_weeks_ago_other": "{n} weeks ago",
        "impressum_title": "Legal notice",
        "impressum_language_note": "This legal notice is required under German law (§5 TMG) and is provided in German.",
        "duration_under30": "< 30 min",
        "duration_30to60": "30-60 min",
        "duration_1to2h": "1-2 hr",
        "duration_over2h": "> 2 hr",
        "age_tag_0_3": "0-3 years and up",
        "age_tag_3_5": "3-5 years and up",
        "age_tag_6_8": "6-8 years and up",
        "age_tag_9_11": "9-11 years and up",
        "age_tag_12_plus": "12 years and up",
        "age_tag_short_0_3": "0-3 years",
        "age_tag_short_3_5": "3-5 years",
        "age_tag_short_6_8": "6-8 years",
        "age_tag_short_9_11": "9-11 years",
        "age_tag_short_12_plus": "12+ years",
        "genre_fairy_tale": "Fairy Tale",
        "genre_adventure": "Adventure",
        "genre_mystery": "Mystery",
        "genre_fantasy": "Fantasy",
        "genre_educational": "Educational",
        "genre_bedtime_story": "Bedtime Story",
        "genre_classic": "Classic",
        "genre_comedy": "Comedy",
        "franchise_disney": "Disney",
        "franchise_pixar": "Pixar",
        "franchise_dreamworks": "DreamWorks",
        "franchise_marvel": "Marvel",
        "franchise_star_wars": "Star Wars",
        "franchise_bibi_blocksberg": "Bibi Blocksberg",
        "franchise_benjamin_bluemchen": "Benjamin Blümchen",
        "franchise_die_drei_fragezeichen": "The Three Question Marks",
        "franchise_tkkg": "TKKG",
        "language_de": "German",
        "language_en": "English",
        "mood_calm": "Calm",
        "mood_funny": "Funny",
        "mood_spooky": "Spooky",
        "mood_adventurous": "Adventurous",
        "mood_heartwarming": "Heartwarming",
        "mood_exciting": "Exciting",
        "mood_silly": "Silly",
        "mood_gentle": "Gentle",
        "seasonal_winter": "Winter",
        "seasonal_christmas": "Christmas",
        "seasonal_halloween": "Halloween",
        "seasonal_easter": "Easter",
        "seasonal_summer": "Summer",
        "seasonal_birthday": "Birthday",
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

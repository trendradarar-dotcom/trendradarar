from __future__ import annotations

from .ledger import LedgerError

C1_UI_LANGUAGE = 'ar'
C1_MARKET_LANGUAGES = frozenset({'ar','en','fr','fa','es'})
C1_MARKET_LANGUAGE_NAMES_AR = {
    'ar': 'العربية',
    'en': 'الإنجليزية',
    'fr': 'الفرنسية',
    'fa': 'الفارسية',
    'es': 'الإسبانية',
}


def normalize_market_language(value: str | None) -> str:
    language = str(value or '').strip().lower()
    if language not in C1_MARKET_LANGUAGES:
        raise LedgerError('C1 market language must be one of ar/en/fr/fa/es')
    return language

import json
from pathlib import Path

LANGUAGES = ("tr", "en", "de")


def detect_language(code: str | None) -> str:
    language = (code or "tr").lower().replace("_", "-").split("-")[0]
    return language if language in LANGUAGES else "tr"


class Translator:
    def __init__(self, directory: Path | None = None):
        root = directory or Path(__file__).parent / "locales"
        self.catalogs = {
            language: json.loads((root / f"{language}.json").read_text(encoding="utf-8"))
            for language in LANGUAGES
        }
        keys = set(self.catalogs["tr"])
        if any(set(catalog) != keys for catalog in self.catalogs.values()):
            raise ValueError("All translations must have identical keys")

    def text(self, language: str, key: str, **values) -> str:
        return self.catalogs[detect_language(language)][key].format(**values)

    def for_language(self, language: str):
        def translate(key: str, **values) -> str:
            return self.text(language, key, **values)

        return translate

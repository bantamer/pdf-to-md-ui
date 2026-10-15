"""List the strings each language still lacks compared with English.

English and Russian are kept complete while features are being built; the
other languages are translated in one pass before a release, and the release
build refuses to go ahead until they are (RELEASE_CHECK in tests/conftest.py).
This prints what that pass has to cover:

    python tools/missing_translations.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import i18n  # noqa: E402

english = i18n.load_table("en")
todo = 0
for code in i18n.LANGUAGES:
    missing = [key for key in english if key not in i18n.load_table(code)]
    todo += len(missing)
    print(f"{code}: {'complete' if not missing else f'{len(missing)} missing'}")
    for key in missing:
        print(f"    {key}: {english[key]!r}")
sys.exit(1 if todo else 0)

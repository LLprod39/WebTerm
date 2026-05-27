import json
import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
src = (FRONTEND_SRC / "lib" / "i18n.tsx").read_text(encoding="utf-8")


def extract_lang_block(text, lang):
    pat = lang + ": {"
    start = text.find(pat)
    if start == -1:
        return {}
    start += len(pat) - 1  # point to opening {
    depth = 0
    pos = start
    while pos < len(text):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                break
        pos += 1
    block = text[start : pos + 1]

    result = {}
    key_val = re.compile(r'"([^"]+)"\s*:\s*"((?:[^\\"]|\\.)*)"')
    for m in key_val.finditer(block):
        key = m.group(1)
        val = m.group(2)
        val = val.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        result[key] = val
    return result


en = extract_lang_block(src, "en")
ru = extract_lang_block(src, "ru")

with (FRONTEND_SRC / "locales" / "en.json").open("w", encoding="utf-8") as f:
    json.dump(en, f, ensure_ascii=False, indent=2)

with (FRONTEND_SRC / "locales" / "ru.json").open("w", encoding="utf-8") as f:
    json.dump(ru, f, ensure_ascii=False, indent=2)

print(f"en.json: {len(en)} keys")
print(f"ru.json: {len(ru)} keys")

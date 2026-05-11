# Translations for Overlay Translate

This directory contains translation files for the Overlay Translate GUI.

## Translation File Format

Translation files use Qt's `.ts` (XML) and `.qm` (compiled binary) formats:

- **`.ts` files**: Human-readable XML files edited with Qt Linguist or text editors
- **`.qm` files**: Compiled binary files loaded by the application at runtime

## File Naming Convention

```
overlay_translate_{language_code}.ts   # Source translation file
overlay_translate_{language_code}.qm   # Compiled translation file
```

Examples:
- `overlay_translate_es.ts` / `overlay_translate_es.qm` - Spanish
- `overlay_translate_zh_CN.ts` / `overlay_translate_zh_CN.qm` - Chinese (Simplified)
- `overlay_translate_fr.ts` / `overlay_translate_fr.qm` - French

## Supported Languages

Currently supported (with ISO 639-1 codes):

| Code | Language | Native Name | RTL |
|------|----------|-------------|-----|
| en | English | English | No |
| es | Spanish | Español | No |
| fr | French | Français | No |
| de | German | Deutsch | No |
| zh_CN | Chinese (Simplified) | 简体中文 | No |
| zh_TW | Chinese (Traditional) | 繁體中文 | No |
| ja | Japanese | 日本語 | No |
| ko | Korean | 한국어 | No |
| pt | Portuguese | Português | No |
| ru | Russian | Русский | No |
| ar | Arabic | العربية | **Yes** |
| he | Hebrew | עברית | **Yes** |
| it | Italian | Italiano | No |
| nl | Dutch | Nederlands | No |
| pl | Polish | Polski | No |
| tr | Turkish | Türkçe | No |
| vi | Vietnamese | Tiếng Việt | No |
| th | Thai | ไทย | No |
| hi | Hindi | हिन्दी | No |
| uk | Ukrainian | Українська | No |

## Workflow for Translators

### 1. Extract Strings (Developers)

Extract all translatable strings from Python code:

```powershell
# Install PySide6 tools if not installed
pip install PySide6

# Extract strings to .ts file
pyside6-lupdate gui/*.py -ts translations/overlay_translate_es.ts
```

### 2. Translate Strings (Translators)

**Option A: Qt Linguist (Recommended)**

1. Install Qt Linguist: https://doc.qt.io/qt-6/linguist-translators.html
2. Open `.ts` file in Qt Linguist
3. Translate each string
4. Mark strings as "Done" after translation
5. Save file

**Option B: Text Editor**

Edit `.ts` file manually:

```xml
<message>
    <source>Capture (F1)</source>
    <translation>Capturar (F1)</translation>
</message>
```

### 3. Compile Translations (Developers)

Compile `.ts` to `.qm` for runtime use:

```powershell
pyside6-lrelease translations/overlay_translate_es.ts
```

This creates `overlay_translate_es.qm` in the same directory.

### 4. Test Translation

1. Start Overlay Translate
2. Go to Settings → All Settings (Ctrl+,)
3. General tab → Interface Language
4. Select your language
5. UI should update immediately

## Translation Guidelines

### String Formatting

- **Keep placeholders**: `{0}`, `{1}`, `%1`, `%2` must remain unchanged
- **Preserve hotkeys**: `&File` → `&Archivo` (keep ampersand position)
- **Match tone**: Professional, concise, user-friendly

### Context Matters

Pay attention to the context tag:

```xml
<message>
    <location filename="control_window.py" line="177"/>
    <source>Capture (F1)</source>
    <translation type="unfinished"></translation>
</message>
```

### Special Strings

- **Keyboard shortcuts**: Keep functional keys in English (`F1`, `Ctrl`, `Shift`)
- **File paths**: Don't translate paths like `Support Folder`
- **Technical terms**: OCR, API, JSON, etc. usually stay in English
- **Emojis**: Can remain or be culturally adapted

### Right-to-Left (RTL) Languages

For Arabic and Hebrew:
- Text direction is handled automatically
- UI layout mirrors (buttons, menus flip horizontally)
- Keep English technical terms in LTR direction
- Test thoroughly to ensure readability

## Quality Checklist

Before submitting a translation:

- [ ] All strings translated (no `type="unfinished"`)
- [ ] Placeholders preserved (`{0}`, `%1`, etc.)
- [ ] Hotkeys preserved (`&` ampersands)
- [ ] Tested in application
- [ ] No grammar/spelling errors
- [ ] Consistent terminology
- [ ] Natural phrasing (not literal translation)

## Contributing Translations

1. Fork the repository
2. Create a new branch: `git checkout -b translation-{language}`
3. Add/edit `.ts` file for your language
4. Compile to `.qm` and test
5. Commit both `.ts` and `.qm` files
6. Submit pull request with description:
   - Language name
   - Translation completeness (e.g., "100% translated, tested")
   - Any cultural adaptations made

## Automation Scripts

### Update all translations

```powershell
# Windows PowerShell
foreach ($file in Get-ChildItem translations\*.ts) {
    pyside6-lrelease $file.FullName
}
```

```bash
# Linux/macOS
for file in translations/*.ts; do
    pyside6-lrelease "$file"
done
```

### Extract strings for all languages

```powershell
$languages = @("es", "fr", "de", "zh_CN", "ja", "ko", "pt", "ru", "ar")
foreach ($lang in $languages) {
    pyside6-lupdate gui/*.py -ts "translations/overlay_translate_$lang.ts"
}
```

## Translation Status

| Language | Progress | Translator | Last Updated |
|----------|----------|------------|--------------|
| English | 100% (Default) | - | - |
| Spanish | 0% | *Needed* | - |
| French | 0% | *Needed* | - |
| German | 0% | *Needed* | - |
| Chinese (S) | 0% | *Needed* | - |
| Chinese (T) | 0% | *Needed* | - |
| Japanese | 0% | *Needed* | - |
| Korean | 0% | *Needed* | - |
| Portuguese | 0% | *Needed* | - |
| Russian | 0% | *Needed* | - |
| Arabic | 0% | *Needed* | - |
| Hebrew | 0% | *Needed* | - |
| Italian | 0% | *Needed* | - |
| Dutch | 0% | *Needed* | - |
| Polish | 0% | *Needed* | - |
| Turkish | 0% | *Needed* | - |
| Vietnamese | 0% | *Needed* | - |
| Thai | 0% | *Needed* | - |
| Hindi | 0% | *Needed* | - |
| Ukrainian | 0% | *Needed* | - |

## Resources

- **Qt Linguist Manual**: https://doc.qt.io/qt-6/qtlinguist-index.html
- **PySide6 i18n Guide**: https://doc.qt.io/qtforpython-6/tutorials/basictutorial/translations.html
- **Translation Best Practices**: https://doc.qt.io/qt-6/linguist-translators.html

## Need Help?

- Open an issue on GitHub with tag `translation`
- Join our community discussions
- Email: translations@overlaytr anslate.com (if available)

---

**Thank you for contributing to making Overlay Translate accessible to users worldwide!** 🌍

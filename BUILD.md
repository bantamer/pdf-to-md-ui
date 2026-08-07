# Сборка Windows-установщика

Важно: PyInstaller не умеет кросс-компиляцию. Windows-exe собирается **только
на Windows** — на macOS получится macOS-приложение. Вариант без своей машины:
GitHub Actions с раннером `windows-latest`.

## Быстрый путь: build.bat

На Windows достаточно дважды кликнуть [build.bat](build.bat) в папке проекта.
Скрипт сам делает всё, что описано ниже: заводит `.venv`, ставит зависимости,
собирает урезанную JRE через `jlink`, запускает PyInstaller и, если найдёт Inno
Setup, собирает установщик.

Что нужно поставить заранее:

| Нужно | Зачем | Если нет |
|---|---|---|
| [Python 3.10+](https://www.python.org/downloads/windows/) (галочка «Add python.exe to PATH») | обязателен | скрипт остановится |
| [JDK 17+](https://adoptium.net) | `jlink` для встроенной Java | соберётся без JRE, тогда Java 11+ нужна на машине пользователя |
| [Inno Setup](https://jrsoftware.org/isdl.php) | Setup.exe для раздачи | соберётся только папка `dist\PDF to Markdown\` |

Результат — `dist\PDF to Markdown\PDF to Markdown.exe`. Это onedir-сборка:
копировать нужно папку целиком, не один exe. JRE скрипт кладёт внутрь этой же
папки, так что скопированная папка работает сама по себе.

Дальше — то же самое руками, по шагам.

## 1. Окружение

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
```

## 2. Урезанная JRE

Пакет `opendataloader-pdf` запускает Java 11+. Чтобы пользователю не пришлось
ставить её самому, кладём рядом собственную. Нужен любой JDK 17+ на машине
сборки (Temurin подойдёт):

```
jlink --add-modules java.base,java.desktop,java.logging,java.naming,java.xml ^
      --strip-debug --no-header-files --no-man-pages --compress=2 ^
      --output jre
```

Получается около 45 МБ. Набор модулей минимальный из рабочих: если при
конвертации вылетит `NoClassDefFoundError`, добавьте нужный модуль или
соберите с `--add-modules ALL-MODULE-PATH` и урежьте потом. На JDK 21+ ключ
`--compress=2` убран — там просто выбросьте его.

Приложение само найдёт эту папку — `_use_bundled_jre()` в
[gui.py](gui.py) выставляет `JAVA_HOME`, если рядом с exe лежит `jre\`.
Java, уже установленная у пользователя, имеет приоритет.

## 3. Сборка приложения

```
pyinstaller app.spec
```

Результат — `dist\PDF to Markdown\`. Проверьте, что внутри лежит jar из
`opendataloader_pdf`; если нет, значит `collect_all` его не подхватил —
добавьте путь к jar в `datas` вручную.

Затем скопируйте туда JRE из шага 2 — приложение ищет её рядом с exe, и
установщик берёт всё одной папкой:

```
robocopy jre "dist\PDF to Markdown\jre" /e
```

## 4. Установщик

Поставьте [Inno Setup](https://jrsoftware.org/isdl.php), затем:

```
iscc installer.iss
```

На выходе `Output\PDF-to-Markdown-Setup.exe`. Ставится в профиль
пользователя, без прав администратора и без запроса UAC.

## Ожидаемые размеры

| Часть | Размер |
|---|---|
| Qt + Python | ~55 МБ |
| JRE после jlink | ~45 МБ |
| jar opendataloader | ~30 МБ |
| Установщик после lzma2 | ~50–60 МБ |

## Что проверить перед раздачей

- Запуск на чистой Windows без Python и без Java.
- PDF с кириллицей в имени файла и в пути.
- Путь с пробелами (`C:\Users\Иван Петров\Мои файлы`).
- Скан без текстового слоя — с галочкой OCR и без неё.

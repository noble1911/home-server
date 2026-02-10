#!/usr/bin/env bash
# Auto-import ebooks from qBittorrent downloads into Calibre library.
# Runs as a persistent service inside the calibre-web container.
# Scans /downloads/Complete/Books for epub/mobi/pdf/azw3 files every 60s.

DOWNLOADS="/downloads/Complete/Books"
LIBRARY="/books"
IMPORTED="/downloads/imported"
EXTENSIONS="epub mobi pdf azw3"

mkdir -p "$IMPORTED" "$DOWNLOADS"

# Ensure Calibre library exists before we start importing
if [ ! -f "$LIBRARY/metadata.db" ]; then
    echo "[book-import] Creating Calibre library at $LIBRARY"
    calibredb --with-library "$LIBRARY" list_categories > /dev/null 2>&1 || true
    # Calibre-Web expects books.isbn and books.flags columns
    sqlite3 "$LIBRARY/metadata.db" \
        "ALTER TABLE books ADD COLUMN isbn TEXT DEFAULT '';
         ALTER TABLE books ADD COLUMN flags INTEGER NOT NULL DEFAULT 1;" 2>/dev/null || true
fi

while true; do
    for ext in $EXTENSIONS; do
        find "$DOWNLOADS" -maxdepth 2 -iname "*.$ext" -type f 2>/dev/null | while read -r file; do
            filename="$(basename "$file")"

            # Skip if already imported
            if [ -f "$IMPORTED/$filename" ]; then
                continue
            fi

            echo "[book-import] Importing: $filename"
            if calibredb add "$file" --with-library "$LIBRARY" 2>&1; then
                # Mark as imported and remove source to save disk space
                touch "$IMPORTED/$filename"
                rm -f "$file"
                echo "[book-import] Success: $filename"
            else
                echo "[book-import] Failed: $filename"
            fi
        done
    done

    sleep 60
done

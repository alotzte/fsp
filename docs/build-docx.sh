#!/bin/sh
# Документация к сдаче (ТЗ §5.2) одним DOCX: docs/fsp-documentation.docx. PDF — печатью DOCX.
# Нужен только Docker: pandoc запускается в контейнере.
set -eu
cd "$(dirname "$0")/.."
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" pandoc/core:3.6 \
  README.md \
  docs/architecture.md \
  docs/compliance.md \
  docs/validation-assessment.md \
  docs/validation-matching.md \
  docs/validation-resume.md \
  docs/libraries.md \
  --from gfm --toc --toc-depth=2 \
  --metadata title="ФСП Карьера — документация" \
  --metadata lang=ru-RU \
  -o docs/fsp-documentation.docx
echo "docs/fsp-documentation.docx"

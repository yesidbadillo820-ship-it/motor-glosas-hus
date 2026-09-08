#!/usr/bin/env bash
# Deja el entorno listo para que la suite de pruebas corra COMPLETA.
#
# Sin esto, doce pruebas fallan por motivos que no tienen nada que ver con el
# código: `tests/test_tools/test_office_tools.py` y `test_dividir_y_pdf.py`
# necesitan LibreOffice de verdad (no solo el ejecutable: Writer, Calc y Draw),
# y `test_msg_tools.py` necesita extract-msg.
#
# Lo usa el CI (.github/workflows/ci.yml) y sirve igual en un contenedor de
# desarrollo:  bash scripts/preparar_entorno_pruebas.sh
set -euo pipefail

echo "== LibreOffice (Writer, Calc, Draw, Impress) =="
# LibreOffice se puede instalar a pedazos: es normal quedarse con
# `libreoffice-core` —el ejecutable— sin ningún módulo que abra documentos.
# Ahí `soffice` arranca y la conversión falla con «source file could not be
# loaded», que parece un archivo dañado y no lo es.
#
# Se MIRA antes de instalar. Los runners de GitHub ya traen LibreOffice
# completo: correr apt-get igual serían dos minutos por cada corrida del CI
# y una dependencia más de la red que se puede caer sin que nada esté mal.
falta_lo() {
  python - <<'PYCHK'
import sys
sys.path.insert(0, "tools/suite_cartera_hus")
try:
    from nucleo import office_tools
except Exception:
    sys.exit(0)  # no se pudo mirar: mejor instalar
sys.exit(0 if (not office_tools.hay_libreoffice() or office_tools.modulos_libreoffice_faltantes()) else 1)
PYCHK
}

if falta_lo; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "   Faltan módulos: instalando…"
    SUDO=""
    [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO apt-get update -qq
    $SUDO apt-get install -y --no-install-recommends \
      libreoffice-writer libreoffice-calc libreoffice-draw libreoffice-impress
  else
    echo "   FALTAN módulos de LibreOffice y no hay apt-get para instalarlos."
    echo "   En Windows: reinstale LibreOffice con la instalación completa."
  fi
else
  echo "   Ya está completo, no hay nada que instalar."
fi

echo "== extract-msg (lectura de correos .msg) =="
if python -c "
import sys; sys.path.insert(0,'tools/suite_cartera_hus')
from nucleo import msg_tools
sys.exit(0 if msg_tools.extract_msg is not None else 1)" 2>/dev/null; then
  echo "   Ya está instalado."
else
# extract-msg declara como obligatoria `red-black-tree-mod`, cuyo instalador
# antiguo (setup.py install) ya no compila con setuptools moderno. Esa pieza
# solo hace falta para RE-ESCRIBIR archivos .msg; `nucleo/msg_tools.py` solo
# los LEE. Por eso se instala sin sus dependencias y se ponen a mano las que
# de verdad se usan.
  pip install --no-deps extract-msg
  pip install olefile beautifulsoup4 compressed-rtf ebcdic RTFDE tzlocal
fi

echo "== Comprobación =="
python - <<'PY'
import shutil
import sys

sys.path.insert(0, "tools/suite_cartera_hus")
from nucleo import office_tools  # noqa: E402

faltan = office_tools.modulos_libreoffice_faltantes()
problemas = []
if not shutil.which("soffice"):
    problemas.append("no se encuentra el ejecutable de LibreOffice")
if faltan:
    problemas.append("faltan módulos de LibreOffice: " + ", ".join(faltan))
# Se importa POR msg_tools y no directo: `red-black-tree-mod` sigue sin
# instalarse (su setup.py ya no compila), y msg_tools pone un stub en su
# lugar porque esa pieza solo hace falta para re-escribir .msg, no para
# leerlos. Comprobar el import a secas daría una falla que no existe.
from nucleo import msg_tools  # noqa: E402

if msg_tools.extract_msg is None:
    problemas.append("extract-msg no quedó instalado (msg_tools no lo encuentra)")

if problemas:
    for p in problemas:
        print("   FALTA:", p)
    sys.exit(1)
print("   Todo listo: LibreOffice completo y extract_msg disponible.")
PY

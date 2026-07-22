"""Tests del Document Intelligence Service (DIS · Fase 2.1).

Con PDFs SINTÉTICOS de estructura real verifica: fingerprint (páginas, autor,
firma, texto, corruptos, incompletos), calidad A–D/X por señales verificables,
clasificación con confianza, duplicados exactos y funcionales, AG016 Curator,
AG017 Storage, AG018 Ingesta, y el criterio de aceptación:
`perfil HUS528043` → el objeto documental completo con timeline y expediente.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_documento as dis  # noqa: E402
import hospiai_indexador as idx  # noqa: E402
from hospiai_sdk import Mision  # noqa: E402

PDF_TEXTO_FIRMADO = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 4>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 5 0 R>>>>/Rotate 0>>endobj\n"
    b"4 0 obj<</Author(KARIN)/Producer(ScanHUS)/CreationDate(D:20260715120000)>>endobj\n"
    b"6 0 obj<</Type/Sig/ByteRange[0 100 200 300]>>endobj\n"
    b"%%EOF\n"
)
PDF_ESCANEO_PURO = (
    b"%PDF-1.4\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 2>>endobj\n"
    b"3 0 obj<</Type/Page/Resources<</XObject<</Im1 7 0 R>>>>/Rotate 90>>endobj\n"
    b"%%EOF\n"
)
PDF_CORRUPTO = b"ESTO NO ES UN PDF, es basura binaria \x00\x01"
PDF_SIN_EOF = b"%PDF-1.4\n2 0 obj<</Type/Pages/Count 1>>endobj\n3 0 obj<</Type/Page/Resources<</Font<</F1 1 0 R>>>>>>endobj\n"


def _escribir(ruta: Path, datos: bytes) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(datos)
    return ruta


class TestFingerprint:
    def test_pdf_completo_con_texto_y_firma(self, tmp_path):
        f = _escribir(tmp_path / "DQX_900006037_HUS528043.pdf", PDF_TEXTO_FIRMADO)
        fp = dis.fingerprint_pdf(f)
        assert fp["paginas"] == 4
        assert fp["autor"] == "KARIN" and fp["productor"] == "ScanHUS"
        assert fp["fecha_creacion_doc"] == "2026-07-15"
        assert fp["firma"] == 1 and fp["texto"] == 1 and fp["problema"] == ""
        assert len(fp["hash"]) == 32
        assert dis.calificar(fp) == "A"

    def test_escaneo_puro_sin_texto(self, tmp_path):
        f = _escribir(tmp_path / "EPICRISIS.pdf", PDF_ESCANEO_PURO)
        fp = dis.fingerprint_pdf(f)
        assert fp["texto"] == 0 and fp["firma"] == 0
        assert fp["rotacion"] == 90 and fp["paginas"] == 2
        assert dis.calificar(fp) == "C"  # necesitará OCR

    def test_corrupto_y_vacio_e_incompleto(self, tmp_path):
        corrupto = dis.fingerprint_pdf(_escribir(tmp_path / "c.pdf", PDF_CORRUPTO))
        assert corrupto["problema"].startswith("CORRUPTO")
        assert dis.calificar(corrupto) == "X"
        vacio = dis.fingerprint_pdf(_escribir(tmp_path / "v.pdf", b""))
        assert vacio["problema"] == "VACIO" and dis.calificar(vacio) == "X"
        inc = dis.fingerprint_pdf(_escribir(tmp_path / "i.pdf", PDF_SIN_EOF))
        assert inc["problema"].startswith("INCOMPLETO")
        assert dis.calificar(inc) == "D"

    def test_dpi_y_legibilidad_quedan_para_ocr(self, tmp_path):
        # Honestidad: el DIS no inventa medidas que no puede tomar sin OCR.
        f = _escribir(tmp_path / "x.pdf", PDF_TEXTO_FIRMADO)
        fp = dis.fingerprint_pdf(f)
        assert "dpi" not in fp and "legibilidad" not in fp  # solo columnas, nunca inventadas


class TestClasificacionConfianza:
    def test_token_directo_maxima_confianza(self):
        cod, _clase, conf = dis.clasificar_con_confianza("DQX_900006037_HUS1.pdf", "1")
        assert cod == "DQX" and conf == 0.98

    def test_alias_reconocido(self):
        cod, _c, conf = dis.clasificar_con_confianza("EPICRISIS.pdf", "1")
        assert cod == "EPI" and conf == 0.9

    def test_generico_solo_carpeta(self):
        cod, _c, conf = dis.clasificar_con_confianza("documento_raro.pdf", "528043")
        assert cod == "ADM" and conf == 0.5

    def test_sin_evidencia(self):
        assert dis.clasificar_con_confianza("documento_raro.pdf", "")[2] == 0.3


class TestPerfilesYDuplicados:
    def _base(self, tmp_path) -> Path:
        share = tmp_path / "y" / "EPS" / "HUS528043"
        _escribir(share / "DQX_900006037_HUS528043.pdf", PDF_TEXTO_FIRMADO)
        _escribir(share / "COPIA_DQX.pdf", PDF_TEXTO_FIRMADO)  # duplicado EXACTO
        _escribir(share / "DQX_v2_900006037_HUS528043.pdf", PDF_ESCANEO_PURO)  # funcional
        _escribir(share / "roto.pdf", PDF_CORRUPTO)
        idx.indexar_raiz(str(tmp_path / "y"), tmp_path / "indices", progreso=lambda m: None)
        return idx.db_de(str(tmp_path / "y"), tmp_path / "indices")

    def test_perfila_y_detecta_duplicados(self, tmp_path):
        db = self._base(tmp_path)
        r = dis.perfilar_base(db, progreso=lambda m: None)
        assert r["perfilados_ahora"] == 4 and r["corruptos"] == 1
        assert r["dup_exactos"] == 1  # la COPIA apunta al original
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        perfiles = {
            Path(f["ruta"]).name: dict(f) for f in con.execute("SELECT * FROM document_profile")
        }
        con.close()
        # Convención: el canónico es el PRIMERO alfabético (COPIA_DQX.pdf aquí);
        # los demás con el mismo hash apuntan a él.
        assert perfiles["COPIA_DQX.pdf"]["dup_exacto_de"] == ""
        assert perfiles["DQX_900006037_HUS528043.pdf"]["dup_exacto_de"].endswith("COPIA_DQX.pdf")
        # Duplicado FUNCIONAL: dos DQX distintos para la misma factura.
        assert perfiles["DQX_900006037_HUS528043.pdf"]["dup_funcional"] == 1
        assert perfiles["DQX_v2_900006037_HUS528043.pdf"]["dup_funcional"] == 1
        # Re-perfilar solo_nuevos no repite trabajo.
        assert dis.perfilar_base(db, progreso=lambda m: None)["perfilados_ahora"] == 0


class TestAgentesDIS:
    def test_curator_detecta_problemas(self, tmp_path):
        TestPerfilesYDuplicados()._base(tmp_path)
        res = dis.AgenteDocumentCurator().ejecutar(
            Mision(codigo="M", tipo="CURAR_DOCUMENTOS"),
            {"dir_indices": tmp_path / "indices", "db_path": tmp_path / "h.db"},
        )
        assert res.resultado == "OK"
        tipos = {p["tipo"] for p in res.salida["problemas"]}
        assert "DOC_CORRUPTO" in tipos and "DOC_DUPLICADO_EXACTO" in tipos
        assert "DOC_SIN_TEXTO" in tipos  # el escaneo puro, listo para avisar al OCR

    def test_storage_optimizer_reporta_gb_y_recuperables(self, tmp_path):
        TestPerfilesYDuplicados()._base(tmp_path)
        dis.perfilar_base(
            idx.db_de(str(tmp_path / "y"), tmp_path / "indices"), progreso=lambda m: None
        )
        res = dis.AgenteStorageOptimizer().ejecutar(
            Mision(codigo="M", tipo="OPTIMIZAR_ALMACENAMIENTO"),
            {"dir_indices": tmp_path / "indices"},
        )
        assert res.resultado == "OK"
        g = res.salida["almacenamiento"][0]
        assert g["archivos"] == 4 and g["dup_exactos"] == 1
        assert g["gb_recuperables"] >= 0

    def test_ingesta_perfila_lo_nuevo_y_avisa_al_expediente(self, tmp_path):
        share = tmp_path / "y" / "EPS" / "HUS600021"
        _escribir(share / "HEV_900006037_HUS600021.pdf", PDF_TEXTO_FIRMADO)
        ctx = {"dir_indices": tmp_path / "indices", "db_path": tmp_path / "h.db"}
        import hospiai_db

        hospiai_db.abrir(tmp_path / "h.db").close()  # expediente vacío pero existente
        res = dis.AgenteIngesta().ejecutar(
            Mision(codigo="M", tipo="INGESTA", datos={"raiz": str(tmp_path / "y")}), ctx
        )
        assert res.resultado == "OK"
        assert res.salida["ingeridos"]["nuevos"] == 1
        assert res.salida["ingeridos"]["perfilados"] == 1
        con = sqlite3.connect(tmp_path / "h.db")
        ev = con.execute(
            "SELECT tipo, factura_norm FROM eventos WHERE tipo='DOCUMENTO_NUEVO'"
        ).fetchone()
        con.close()
        assert ev is not None and ev[1] == "600021"


class TestCriterioAceptacion:
    def test_perfil_de_factura_completo(self, tmp_path, capsys):
        TestPerfilesYDuplicados()._base(tmp_path)
        dis.perfilar_base(
            idx.db_de(str(tmp_path / "y"), tmp_path / "indices"), progreso=lambda m: None
        )
        p = dis.perfil_factura("HUS528043", tmp_path / "indices", tmp_path / "no_exp.db")
        assert p["clave"] == "528043"
        docs = {d["nombre"]: d for d in p["documentos"]}
        dqx = docs["DQX_900006037_HUS528043.pdf"]
        assert dqx["codigo"] == "DQX" and "quirúrgica" in dqx["clase"].lower()
        assert dqx["calidad"] == "A" and dqx["confianza"] == 0.98
        assert dqx["paginas"] == 4 and dqx["texto"] == 1 and dqx["firma"] == 1
        assert dqx["creado"] and dqx["perfilado_en"]
        # Y el comando imprime el objeto documental legible.
        assert dis.main(["--indices", str(tmp_path / "indices"), "--db",
                         str(tmp_path / "no_exp.db"), "perfil", "HUS528043"]) == 0  # fmt: skip
        out = capsys.readouterr().out
        assert "OBJETO DOCUMENTAL" in out and "Calidad   : A" in out
        assert "Firma: Sí" in out and "Timeline" in out

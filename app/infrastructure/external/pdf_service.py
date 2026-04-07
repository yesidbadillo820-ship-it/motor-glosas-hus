import io
import json
import logging
import pdfplumber
import PyPDF2

logger = logging.getLogger("pdf_service")


class PdfService:
    async def extraer(self, file_content: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._procesar_pdf_sync, file_content)

    def _procesar_pdf_sync(self, file_content: bytes) -> str:
        logger.info("Iniciando extracción de PDF")
        paginas = []
        
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                logger.info(f"PDF abierto con {len(pdf.pages)} páginas")
                for i, page in enumerate(pdf.pages):
                    txt = page.extract_text() or ""
                    for table in page.extract_tables() or []:
                        for row in table:
                            txt += " | ".join(
                                [str(c).replace("\n", " ") if c else "" for c in row]
                            ) + "\n"
                    paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
                    
        except Exception as e:
            logger.warning(f"pdfplumber falló, usando PyPDF2: {e}")
            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            for i in range(len(reader.pages)):
                txt = reader.pages[i].extract_text() or ""
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")

        if not paginas:
            logger.warning("PDF sin contenido extraer")
            return ""

        if len(paginas) <= 4:
            return "".join(paginas)

        inicio = "".join(paginas[:2])
        fin = "".join(paginas[-2:])
        medio = "".join(paginas[2:-2])

        resultado = (
            inicio[:3000] + 
            "\n...[PÁGINAS INTERMEDIAS OMITIDAS]...\n" + 
            medio[:2000] + 
            "\n...\n" + 
            fin[:2000]
        )
        
        logger.info(f"PDF procesado: {len(resultado)} caracteres")
        return resultado

    async def extraer_multiple(self, archivos: list[bytes]) -> str:
        resultados = []
        for archivo in archivos:
            contenido = await self.extraer(archivo)
            resultados.append(contenido)
        return "\n\n--- DOCUMENTO SIGUIENTE ---\n\n".join(resultados)
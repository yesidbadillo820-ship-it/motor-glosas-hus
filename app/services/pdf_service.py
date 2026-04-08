import io
import asyncio
import logging
import pdfplumber
import PyPDF2

logger = logging.getLogger("motor_glosas")

class PdfService:
    """
    Servicio dedicado exclusivamente a la extracción y procesamiento
    de texto desde archivos PDF.
    """
    
    async def extraer(self, file_content: bytes) -> str:
        """
        Ejecuta la extracción de forma asíncrona. 
        Al usar run_in_executor evitamos bloquear el event loop de FastAPI 
        mientras el servidor lee PDFs pesados (evita que el servidor se "congele" para otros usuarios).
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._procesar_pdf_sync, file_content)

    def _procesar_pdf_sync(self, file_content: bytes) -> str:
        """
        Lógica síncrona real de extracción usando pdfplumber y PyPDF2 como respaldo.
        """
        paginas = []
        try:
            # Intento primario con pdfplumber (excelente para extraer tablas de facturas)
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for i, page in enumerate(pdf.pages):
                    txt = page.extract_text() or ""
                    # Extraer tablas si las hay
                    for table in page.extract_tables() or []:
                        for row in table:
                            txt += " | ".join(
                                [str(c).replace("\n", " ") if c else "" for c in row]
                            ) + "\n"
                    paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")
                    
        except Exception as e:
            logger.warning(f"Fallo pdfplumber, usando PyPDF2 como respaldo: {e}")
            # Fallback con PyPDF2 (más rápido, útil si el PDF está corrupto para pdfplumber)
            reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            for i in range(len(reader.pages)):
                txt = reader.pages[i].extract_text() or ""
                paginas.append(f"\n--- PÁG {i+1} ---\n{txt}")

        if not paginas:
            return ""

        # ---------------------------------------------------------
        # Estrategia inteligente para no saturar el prompt de la IA:
        # Se priorizan las primeras 2 páginas (encabezados/paciente) 
        # y las últimas 2 (firmas/totales).
        # ---------------------------------------------------------
        if len(paginas) <= 4:
            return "".join(paginas)

        inicio = "".join(paginas[:2])
        fin    = "".join(paginas[-2:])
        medio  = "".join(paginas[2:-2])

        # Presupuesto: 3000 caracteres al inicio + 2000 del medio + 2000 al final
        resultado = (
            inicio[:3000] + 
            "\n...[PÁGINAS INTERMEDIAS OMITIDAS PARA AHORRAR MEMORIA DE IA]...\n" + 
            medio[:2000] + 
            "\n...\n" + 
            fin[:2000]
        )
        return resultado

import io
import base64
import asyncio
import logging
import httpx
import pdfplumber
import PyPDF2

logger = logging.getLogger("motor_glosas")

# Umbral por debajo del cual consideramos que el PDF es escaneado (sin
# texto extraíble nativamente) y vale la pena intentar OCR con Claude.
UMBRAL_TEXTO_MINIMO = 150

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

    async def extraer_con_ocr(
        self,
        file_content: bytes,
        anthropic_api_key: str = "",
        anthropic_model: str = "claude-sonnet-4-6",
    ) -> tuple[str, str]:
        """Intenta extracción nativa; si el texto es pobre y hay Anthropic,
        manda el PDF a Claude para transcripción (OCR vision).

        Retorna (texto, metodo) donde metodo ∈ {"nativo", "anthropic-vision", "vacio"}.
        """
        texto = await self.extraer(file_content)
        # Medir texto real (sin markers de página)
        texto_real = "".join([l for l in texto.split("\n") if "--- PÁG" not in l]).strip()

        if len(texto_real) >= UMBRAL_TEXTO_MINIMO:
            return texto, "nativo"

        if not anthropic_api_key:
            logger.warning(
                f"PDF con texto pobre ({len(texto_real)} chars) y sin ANTHROPIC_API_KEY; "
                "devolviendo lo extraído nativamente."
            )
            return texto, "vacio"

        logger.info(
            f"PDF parece escaneado ({len(texto_real)} chars nativos). "
            f"Enviando a Claude vision para OCR…"
        )
        try:
            texto_ocr = await self._ocr_anthropic(
                file_content, anthropic_api_key, anthropic_model
            )
            if texto_ocr and len(texto_ocr.strip()) > len(texto_real):
                return texto_ocr, "anthropic-vision"
            return texto, "vacio"
        except Exception as e:
            logger.error(f"OCR anthropic falló: {e}")
            return texto, "vacio"

    async def _ocr_anthropic(
        self, pdf_bytes: bytes, api_key: str, model: str
    ) -> str:
        """Envía el PDF a Claude como document base64 y pide la transcripción."""
        if len(pdf_bytes) > 32 * 1024 * 1024:  # 32 MB limit Anthropic PDFs
            raise RuntimeError("PDF excede 32 MB, no se puede enviar a Anthropic")

        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        prompt = (
            "Transcribe fielmente todo el contenido textual de este documento PDF. "
            "Mantén la estructura (tablas, encabezados, filas). No resumas. No interpretes. "
            "Si hay tablas con columnas: FACTURA, CÓDIGO GLOSA, VALOR OBJETADO, OBSERVACIÓN, "
            "preserva el orden de las columnas separando con ' | '. "
            "Entrega solo el texto transcrito, sin preámbulos ni comentarios adicionales."
        )

        _timeout = httpx.Timeout(connect=15.0, read=180.0, write=60.0, pool=10.0)
        async with httpx.AsyncClient(timeout=_timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 8000,
                    "temperature": 0.0,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_b64,
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                },
            )
            data = resp.json()
            if "content" in data and data["content"]:
                return data["content"][0].get("text", "")
            err = data.get("error", {}).get("message", str(data)[:400])
            raise RuntimeError(f"Anthropic OCR error: {err}")

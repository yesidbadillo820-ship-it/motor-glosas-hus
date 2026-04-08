"""
Pytest configuration and shared fixtures for Motor Glosas HUS tests.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def glosa_service():
    """Provide GlosaService instance without API keys for testing."""
    from app.services.glosa_service import GlosaService
    return GlosaService(groq_api_key=None, anthropic_api_key=None)


@pytest.fixture
def sample_glosa_input():
    """Sample GlosaInput data for testing."""
    from app.models.schemas import GlosaInput
    return GlosaInput(
        eps="EPS SANITAS",
        fecha_radicacion="2026-03-01",
        fecha_recepcion="2026-03-15",
        numero_factura="FAC-001234",
        numero_radicado="RAD-567890",
        tabla_excel="TA0201 $1,500,000 Diferencia en consulta"
    )


@pytest.fixture
def sample_contratos():
    """Sample contratos database for testing."""
    return {
        "EPS SANITAS": "CONTRATO 2026 - SOAT + 15%",
        "EPS SURA": "CONTRATO 2026 - SOAT + 20%",
        "EPS NUEVA EPS": "SIN CONTRATO - TARIFA SOAT PLENA"
    }


@pytest.fixture
def mock_feriados():
    """Feriado list for testing date calculations."""
    return [
        "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03",
        "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29",
        "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12", "2026-11-02",
        "2026-11-16", "2026-12-08", "2026-12-25"
    ]

from fastapi import APIRouter

from app.schemas.candidates import ConsentDocumentRead
from app.services.consents import CONSENT_DOCUMENTS

router = APIRouter(prefix="/consents", tags=["consents"])


@router.get("/documents")
async def list_consent_documents() -> list[ConsentDocumentRead]:
    """Актуальные тексты согласий. Фронт показывает их перед тем, как пользователь согласится."""
    return [
        ConsentDocumentRead(
            kind=document.kind,
            version=document.version,
            title=document.title,
            text=document.text,
        )
        for document in CONSENT_DOCUMENTS.values()
    ]

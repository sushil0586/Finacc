from numbering.models import DocumentType  # change app path

def get_purchase_documenttype_id_by_doc_code(doc_code: str) -> int:
    dt = DocumentType.objects.filter(module="purchase", default_code=doc_code, is_active=True).first()
    if not dt:
        raise ValueError(f"DocumentType not found for module=purchase doc_code={doc_code}")
    return dt.id

import asyncio
import logging
from app.agents.ocr.agent import OCRAgent
from app.schemas.agent_messages import DocumentEnvelope
from uuid import uuid4

logging.basicConfig(level=logging.INFO)

async def test_ocr():
    agent = OCRAgent()
    
    # We need a valid envelope that points to a test file in minio
    # Or we can just mock storage_service to read a local file
    import app.agents.ocr.agent
    import os
    
    class MockStorage:
        async def download_document(self, path):
            with open(path, "rb") as f:
                return f.read()
                
    app.agents.ocr.agent.storage_service = MockStorage()
    
    # Find a test pdf
    test_pdf = r"a:\PROJECTS\LMIS PROJECT\LMIS\data\raw\test_lab.pdf"
    
    # Create a dummy pdf if it doesn't exist to test layout
    if not os.path.exists(test_pdf):
        print(f"Test pdf not found at {test_pdf}")
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), "Hemoglobin (Hb) = 13.2 g/dL")
        page.insert_text(fitz.Point(50, 70), "Fasting Blood Sugar = 102 mg/dL")
        page.insert_text(fitz.Point(50, 90), "LDL Cholesterol = 122 mg/dL")
        # And an image to test OCR fallback
        # doc.insert_page(1) ...
        doc.save(test_pdf)
        
    env = DocumentEnvelope(
        document_id=uuid4(),
        patient_id=uuid4(),
        storage_path=test_pdf,
        document_type="lab_report",
        quality_score=1.0,
        quality_flags=[],
        routing="ocr",
        metadata={}
    )
    
    res = await agent.extract(env)
    print("Extracted Spans:", len(res.spans))
    print("Full Text:\n", res.full_text)

if __name__ == "__main__":
    asyncio.run(test_ocr())

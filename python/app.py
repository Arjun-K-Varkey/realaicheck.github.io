from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
from detector.misinfo_detector import detect_misinfo

app = FastAPI(
    title="RealAI Check API",
    description="AI Misinformation Detector - Detects AI text & fact-checks claims",
    version="2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

class AnalyzeRequest(BaseModel):
    url: str
    manual_text: Optional[str] = None  # Fallback for blocked sites

@app.get("/")
async def root():
    return {"message": "RealAI Check API is live! 🚀 POST to /analyze with {'url': 'https://realaicheck-github-io.onrender.com'}", "status": "healthy"}

@app.post("/analyze")
async def analyze_url(request: AnalyzeRequest = Body(...)):
    """
    Analyze a news URL for AI generation & misinformation.
    Returns JSON report (same as CLI).
    """
    try:
        if request.manual_text:
            # TODO: Adapt detect_misinfo for direct text (future enhancement)
            raise HTTPException(status_code=501, detail="Manual text support coming soon")
        
        report = detect_misinfo(request.url)
        if report is None:
            raise HTTPException(status_code=503, detail="Fetch failed (e.g., 403 block). Try manual text or different URL.")
        
        return report
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "RealAI Check"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


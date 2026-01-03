from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
# Assuming 'logger' is defined elsewhere, or you can import logging
# from loguru import logger # Example if using loguru
import logging # Standard logging

logger = logging.getLogger(__name__) # Basic logger setup

from detector.misinfo_detector import detect_misinfo

app = FastAPI(
    title="RealAI Check API",
    description="AI Misinformation Detector - Detects AI text & fact-checks claims",
    version="2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# --- CORS Middleware Configuration ---
# This is essential for allowing your GitHub.io frontend to communicate
# with your Render backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins. For production, restrict this to your frontend's URL.
    allow_credentials=True,
    allow_methods=["*"],  # Allows all standard HTTP methods.
    allow_headers=["*"],  # Allows all headers.
)
# --- End CORS Configuration ---

class AnalyzeRequest(BaseModel):
    url: str
    enable_playwright: Optional[bool] = False  # Added to match potential frontend payload
    description: Optional[str] = None        # Added to match potential frontend payload

@app.get("/")
async def root():
    """
    Root endpoint to confirm API is running and CORS is enabled.
    """
    return {
        "message": "RealAI Check API is live! 🚀 POST to /analyze with {'url': 'https://example.com'}",
        "status": "healthy",
        "cors": "✅ Enabled - your GitHub.io site can now connect"
    }

@app.post("/analyze")
async def analyze_url(request: AnalyzeRequest = Body(...)):
    """
    Analyzes a given URL for AI-generated content and misinformation.
    """
    try:
        report = detect_misinfo(request.url)
        
        # Check if the report contains an error dictionary as returned by detect_misinfo
        if isinstance(report, dict) and "error" in report:
            logger.error(f"Detection error for URL {request.url}: {report['error']}")
            raise HTTPException(status_code=503, detail=report["error"])
            
        # Check if the report is None, indicating a general failure
        if report is None:
            logger.error(f"Analysis failed for URL {request.url} - returned None.")
            raise HTTPException(status_code=503, detail="Analysis failed. Try a different URL.")
        
        # If report is valid, return it
        return report
    
    except HTTPException:
        # Re-raise HTTPException to preserve status codes and details
        raise
    except Exception as e:
        # Catch any other unexpected errors during analysis
        logger.exception(f"Unexpected analysis error for URL {request.url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@app.get("/health")
async def health():
    """
    Health check endpoint for the API service.
    """
    return {"status": "ok", "service": "RealAI Check"}

if __name__ == "__main__":
    # Determine the port to run on. Default to 8000 if not specified.
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    # Run the FastAPI application using uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


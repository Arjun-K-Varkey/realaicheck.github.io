import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import os
import logging
from duckduckgo_search import DDGS
from huggingface_hub import InferenceClient

# Setup logging (visible in Render dashboard)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config (tunable for free tier)
CONFIG = {
    "max_text_len": 6000,
    "claim_min_len": 70,
    "claim_max_len": 300,
    "ai_chunk_size": 512,
    "ddg_results": 3,
}

# Hugging Face Inference Client (no local models, works on free Render)
# Make sure to set the HF_TOKEN environment variable in your Render settings!
HF_CLIENT = InferenceClient(
    model="openai-community/roberta-base-openai-detector",
    token=os.getenv("HF_TOKEN")
)

# Step 1: Robust Fetch with Retries
def fetch_content(url):
    """
    Fetches content from a URL with headers, retries, and basic parsing.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'DNT': '1',
    }

    session = requests.Session()
    # Retry strategy for common network issues on free tiers
    retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[403, 429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        response = session.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove common non-content tags
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'iframe']):
            tag.decompose()

        # Find main content area
        article = soup.find('article') or soup.find('main') or soup.find(['div'], class_=re.compile(r'content|article|body')) or soup.body
        text = ' '.join(article.get_text(strip=True).split()) if article else ' '.join(p.get_text(strip=True) for p in soup.find_all('p'))

        # Enhanced cleaning for common web artifacts
        patterns = [
            r'\d+ of \d+\|?',
            r'Read More.*?(of \d+\|?)?',
            r'$$AP Photo[^)]*$$',
            r'THIS IS A BREAKING NEWS UPDATE\.?',
            r'Smoke raises? at .*?Saturday, Jan\.?',
            r'Advertisement \|',
            r'Share this article'
        ]
        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        text = re.sub(r'\s+', ' ', text).strip()
        return text[:CONFIG["max_text_len"]]

    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code}: {url}")
        return f"Error: Site blocked (403/401). Try again later."
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        return f"Error fetching: {str(e)}"

# Step 2: AI Detection via Hugging Face Inference API (FREE, NO LOCAL MODEL)
def is_ai_generated(text):
    """
    Analyzes text for AI generation using Hugging Face Inference API.
    Returns a tuple: (is_likely_ai: bool, confidence_score: float)
    """
    if len(text) < 50: # Too short to reliably detect
        return False, 0.0

    chunks = [text[i:i+CONFIG["ai_chunk_size"]] for i in range(0, len(text), CONFIG["ai_chunk_size"])]
    scores = []

    for chunk in chunks:
        try:
            # Use the HF InferenceClient
            result = HF_CLIENT.text_classification(chunk)
            # The model 'openai-community/roberta-base-openai-detector' labels AI as LABEL_1
            # We want a score where higher means more AI.
            score = result[0].score if result[0].label == 'LABEL_1' else 1 - result[0].score
            scores.append(score)
            logger.debug(f"AI chunk score: {score:.3f}")
        except Exception as e:
            logger.warning(f"AI detection failed for a chunk: {e}")
            scores.append(0.5)  # Use a neutral score if detection fails for a chunk

    if not scores: # Handle case where no chunks could be processed
        return False, 0.0

    avg_score = sum(scores) / len(scores)
    # Consider it AI-generated if the average score is above 0.5
    return avg_score > 0.5, avg_score

# Step 3: Improved Claim Extraction
def extract_claims(text):
    """
    Extracts potential claims (factual statements) from the text.
    """
    # Split into sentences, handling common abbreviations
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
    claims = []
    for sent in sentences:
        sent = sent.strip()
        # Filter by length constraints
        if not (CONFIG["claim_min_len"] <= len(sent) <= CONFIG["claim_max_len"]):
            continue
        # Exclude questions and common irrelevant phrases
        if sent.endswith('?') or any(phrase in sent.lower() for phrase in ['read more', 'ap photo', 'photo']):
            continue

        # Boost sentences containing factual keywords
        factual_keywords = ['said', 'claimed', 'according to', 'reported', 'confirmed', 'strike', 'event']
        if any(kw in sent.lower() for kw in factual_keywords):
            claims.append(sent)
        # If not many claims yet, add sentences with reasonable capitalization
        elif len(claims) < 6:
            words = sent.split()
            caps_ratio = sum(1 for w in words if w and w[0].isupper()) / max(len(words), 1)
            if caps_ratio < 0.7: # Avoid overly shouty sentences
                claims.append(sent)

    return claims[:6]  # Return up to 6 claims for analysis

# Step 4: Fact-Check with DuckDuckGo Search API
def fact_check_claim(claim):
    """
    Uses DuckDuckGo to find supporting and challenging evidence for a claim.
    """
    try:
        with DDGS() as ddgs:
            # Search for confirmation
            support_results = list(ddgs.text(f'"{claim}" confirmed OR true OR evidence', max_results=CONFIG["ddg_results"]))
            # Search for challenges
            challenge_results = list(ddgs.text(f'"{claim}" false OR hoax OR debunked OR misinformation', max_results=CONFIG["ddg_results"]))

        support_links = [r['href'] for r in support_results]
        challenge_links = [r['href'] for r in challenge_results]

        support_count = len(support_links)
        challenge_count = len(challenge_links)

        # Determine verdict based on evidence counts
        if support_count == 0 and challenge_count == 0:
            verdict = "No evidence found"
        elif challenge_count >= 2:
            verdict = "Likely False/Misleading"
        elif support_count >= 2:
            verdict = "Likely True"
        elif challenge_count > support_count:
            verdict = "Leans False"
        elif support_count > challenge_count:
            verdict = "Leans True"
        else:
            verdict = "Inconclusive"

        return {
            "claim": claim[:200] + "..." if len(claim) > 200 else claim, # Truncate long claims
            "support_count": support_count,
            "support_links": support_links[:3], # Limit links shown
            "challenge_count": challenge_count,
            "challenge_links": challenge_links[:3],
            "verdict": verdict
        }
    except Exception as e:
        logger.error(f"Fact-check failed for claim '{claim[:50]}...': {e}")
        return {"claim": claim[:200] + "...", "verdict": "Fact-check error", "support_count": 0, "challenge_count": 0}

# Main analysis function (designed to be called by app.py)
def detect_misinfo(url):
    """
    Orchestrates the detection process: fetching, AI check, claim extraction, and fact-checking.
    Returns a dictionary structured for the FastAPI endpoint.
    """
    logger.info(f"Starting analysis for URL: {url}")

    content = fetch_content(url)
    if content.startswith("Error"):
        logger.warning(f"Analysis aborted due to fetch error: {content}")
        # Return an error structure that app.py can handle
        return {"error": content, "url": url, "analysis_date": datetime.now().isoformat()}

    # Perform AI Detection
    ai_likely, ai_score = is_ai_generated(content)
    logger.info(f"AI detection complete. Score: {ai_score:.3f}. Likely AI: {ai_likely}")

    # Extract and fact-check claims
    claims = extract_claims(content)
    logger.info(f"Extracted {len(claims)} potential claims.")

    checked_claims = []
    false_flags = 0 # Count of claims deemed likely false or leaning false
    for claim in claims:
        check = fact_check_claim(claim)
        checked_claims.append(check)
        # Increment flag if verdict indicates falsehood
        if "False" in check["verdict"] or "Leans False" == check["verdict"]:
            false_flags += 1

    # Determine overall verdict based on AI score and claim checks
    if ai_likely and false_flags >= 1:
        overall_verdict = "🚨 AI Misinfo Likely"
    elif false_flags >= 2:
        overall_verdict = "⚠️ Potential Misinfo"
    elif ai_likely:
        overall_verdict = "🤖 Likely AI (Claims OK)"
    else:
        overall_verdict = "✅ Appears Legit"

    logger.info(f"Overall verdict determined: {overall_verdict}")

    # Structure the result to match your website's expected JSON format
    result = {
        "url": url,
        "analysis_date": datetime.now().isoformat(),
        "ai_detection": {
            "probability_ai": float(ai_score),
            "verdict": "Likely AI" if ai_likely else "Likely Human"
        },
        "claims": checked_claims,
        "overall_verdict": overall_verdict
    }

    logger.info(f"Analysis finished successfully for {url}")
    return result

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from transformers import pipeline
import re
import json
from datetime import datetime
import os
import logging
from duckduckgo_search import DDGS
import argparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config (easy to tweak)
CONFIG = {
    "max_text_len": 6000,
    "claim_min_len": 70,
    "claim_max_len": 300,
    "ai_chunk_size": 512,
    "ddg_results": 3,
    "reports_dir": os.path.expanduser("~/Downloads/realaicheck_reports"),
}

# Step 1: Robust Fetch with Retries
def fetch_content(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
    
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[403, 429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    try:
        response = session.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'header', 'iframe']):
            tag.decompose()
        
        article = soup.find('article') or soup.find('main') or soup.find(['div'], class_=re.compile(r'content|article|body')) or soup.body
        text = ' '.join(article.get_text(strip=True).split()) if article else ' '.join(p.get_text(strip=True) for p in soup.find_all('p'))
        
        # Enhanced cleaning
        patterns = [
            r'\d+ of \d+\|?',
            r'Read More.*?(of \d+\|?)?',
            r'$$AP Photo[^)]*$$',
            r'THIS IS A BREAKING NEWS UPDATE\.?',
            r'Smoke raises? at .*?Saturday, Jan\.?',
            r'Advertisement \|',
            r'Share this article',
        ]
        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:CONFIG["max_text_len"]]
        
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code}: {url}")
        return f"Error: Site blocked (403/401). Paste text manually or try later."
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        return f"Error fetching: {str(e)}"

# Step 2: AI Detection (Chunked for Long Text)
detector = pipeline("text-classification", model="openai-community/roberta-base-openai-detector")

def is_ai_generated(text):
    chunks = [text[i:i+CONFIG["ai_chunk_size"]] for i in range(0, len(text), CONFIG["ai_chunk_size"])]
    scores = []
    for chunk in chunks:
        result = detector(chunk)[0]
        scores.append(1 if result['label'] == 'LABEL_1' else 0)
    
    avg_score = sum(scores) / len(scores)
    return avg_score > 0.5, avg_score

# Step 3: Improved Claim Extraction
def extract_claims(text):
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
    claims = []
    for sent in sentences:
        sent = sent.strip()
        if not (CONFIG["claim_min_len"] <= len(sent) <= CONFIG["claim_max_len"]):
            continue
        if sent.endswith('?') or any(phrase in sent.lower() for phrase in ['read more', 'ap photo', 'photo']):
            continue
        
        # Boost factual sentences
        factual_keywords = ['said', 'claimed', 'according to', 'reported', 'confirmed', 'strike', 'event']
        if any(kw in sent.lower() for kw in factual_keywords):
            claims.append(sent)
        elif len(claims) < 6:  # Relax for fewer claims
            words = sent.split()
            caps_ratio = sum(1 for w in words if w and w[0].isupper()) / max(len(words), 1)
            if caps_ratio < 0.7:
                claims.append(sent)
    
    return claims[:6]  # Up to 6 for better coverage

# Step 4: Fact-Check with DDG
def fact_check_claim(claim):
    with DDGS() as ddgs:
        support_results = list(ddgs.text(f'"{claim}" confirmed OR true OR evidence', max_results=CONFIG["ddg_results"]))
        challenge_results = list(ddgs.text(f'"{claim}" false OR hoax OR debunked OR misinformation', max_results=CONFIG["ddg_results"]))
    
    support_links = [r['href'] for r in support_results]
    challenge_links = [r['href'] for r in challenge_results]
    
    support_count = len(support_links)
    challenge_count = len(challenge_links)
    
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
        "claim": claim[:200] + "..." if len(claim) > 200 else claim,
        "support_count": support_count,
        "support_links": support_links[:3],
        "challenge_count": challenge_count,
        "challenge_links": challenge_links[:3],
        "verdict": verdict
    }

# Main
def detect_misinfo(url):
    logger.info(f"Starting analysis: {url}")
    content = fetch_content(url)
    if content.startswith("Error"):
        print(content)
        logger.warning("Analysis skipped due to fetch error")
        return None
    
    print(f"📄 Snippet: {content[:200]}...\n")
    
    ai_likely, ai_score = is_ai_generated(content)
    print(f"🤖 AI Score: {ai_score:.1%} ({'🔴 Likely AI' if ai_likely else '🟢 Likely Human'})\n")
    
    claims = extract_claims(content)
    print(f"📝 Claims found: {len(claims)}\n" + '\n'.join(f"• {c}" for c in claims) + '\n')
    
    report_data = {
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "ai_score": ai_score,
        "ai_verdict": "Likely AI" if ai_likely else "Likely Human",
        "claims": [],
        "overall": "",
        "config": CONFIG,
        "note": "IFCN-aligned prototype. Human review essential."
    }
    
    false_flags = 0
    for claim in claims:
        check = fact_check_claim(claim)
        report_data["claims"].append(check)
        false_flags += 1 if "False" in check["verdict"] or "Leans False" == check["verdict"] else 0
        
        print(f"✅ {check['verdict']}: {check['claim']}")
        print(f"   Support: {check['support_count']} | Challenge: {check['challenge_count']}\n")
    
    if ai_likely and false_flags >= 1:
        overall = "🚨 AI Misinfo Likely"
    elif false_flags >= 2:
        overall = "⚠️ Potential Misinfo"
    elif ai_likely:
        overall = "🤖 Likely AI (Claims OK)"
    else:
        overall = "✅ Appears Legit"
    
    report_data["overall"] = overall
    print(f"\n🎯 OVERALL: {overall}")
    
    # Save report
    os.makedirs(CONFIG["reports_dir"], exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"realaicheck_{timestamp}.json"
    filepath = os.path.join(CONFIG["reports_dir"], filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Report: {filepath}")
    logger.info(f"Report saved: {filepath}")
    return report_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RealAI Check Detector")
    parser.add_argument("url", nargs="?", help="Website URL")
    args = parser.parse_args()
    
    url = args.url or input("Enter URL: ").strip()
    if url:
        detect_misinfo(url)



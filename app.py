"""
AI Transfer System V4.0 — FZÚ Patent & Research Intelligence
=============================================================
Pipeline: PDF → Gemini multi-query → Google Patents → AI filtr → OpenAlex → Kritická analýza → Docs
Features: retry logic, historie analýz, všechny patenty viditelné, deployment-ready

Spuštění:  pip install streamlit requests PyPDF2 python-docx  &&  streamlit run app.py
"""

import streamlit as st
import requests
import json
import time
import os
import io
import re
import random
import hashlib
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(page_title="AI Transfer System — FZÚ", page_icon="🔬", layout="wide", initial_sidebar_state="expanded")
HISTORY_DIR = Path("analysis_history")
HISTORY_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* === GLOBAL RESET === */
html, body, [class*="st-"], .stMarkdown, .stTextInput label, .stSlider label,
.stFileUploader label, .stButton button, .stTabs [data-baseweb="tab"],
h1, h2, h3, h4, h5, h6, p, span, div {
    font-family: 'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.block-container { max-width: 1080px; padding: 2.5rem 1.5rem 4rem; }

/* === HIDE STREAMLIT BRANDING === */
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
footer::after { content:'AI Transfer System V4 — FZÚ AV ČR'; visibility:visible; display:block; text-align:center; padding:8px; font-size:11px; color:#94a3b8; }

/* === SIDEBAR === */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f1a2e 0%, #162240 100%) !important;
}
[data-testid="stSidebar"] * { color: #c8d6e5 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] .stMarkdown h3 {
    color: #ffffff !important; font-size: 0.85rem !important; text-transform: uppercase;
    letter-spacing: 0.08em !important; font-weight: 600 !important; margin-top: 1rem !important;
}
[data-testid="stSidebar"] .stTextInput input {
    background: rgba(255,255,255,0.06) !important; border: 1px solid rgba(255,255,255,0.12) !important;
    color: #e2e8f0 !important; border-radius: 8px !important; font-size: 13px !important;
}
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #38bdf8 !important; box-shadow: 0 0 0 2px rgba(56,189,248,0.15) !important;
}
[data-testid="stSidebar"] .stSlider [data-baseweb="slider"] div {
    background: #38bdf8 !important;
}
[data-testid="stSidebar"] button {
    background: rgba(255,255,255,0.06) !important; border: 1px solid rgba(255,255,255,0.15) !important;
    color: #e2e8f0 !important; border-radius: 8px !important; width: 100%;
    transition: all 0.15s !important;
}
[data-testid="stSidebar"] button:hover {
    background: rgba(56,189,248,0.15) !important; border-color: #38bdf8 !important;
}
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.08) !important; }

/* === HERO BANNER === */
.hero {
    background: linear-gradient(135deg, #0b1120 0%, #162240 40%, #1e3a5f 70%, #0b1120 100%);
    color: white; padding: 3rem 3rem 2.5rem; border-radius: 20px; margin-bottom: 2rem;
    position: relative; overflow: hidden;
    border: 1px solid rgba(56,189,248,0.1);
}
.hero::before {
    content: ''; position: absolute; top: -80px; right: -60px; width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(56,189,248,0.06) 0%, transparent 70%);
    pointer-events: none;
}
.hero::after {
    content: ''; position: absolute; bottom: -100px; left: -40px; width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(16,185,129,0.04) 0%, transparent 70%);
    pointer-events: none;
}
.hero-badge {
    display: inline-block; background: rgba(56,189,248,0.12); color: #7dd3fc;
    padding: 4px 14px; border-radius: 20px; font-size: 0.7rem; font-weight: 600;
    letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 1rem;
    border: 1px solid rgba(56,189,248,0.15);
}
.hero h1 {
    font-size: 2rem; font-weight: 700; margin: 0 0 0.6rem;
    letter-spacing: -0.03em; line-height: 1.2;
    background: linear-gradient(135deg, #ffffff 0%, #94cef5 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.hero p { font-size: 0.92rem; opacity: 0.55; margin: 0; font-weight: 400; line-height: 1.5; }
.hero-org { font-size: 0.75rem; opacity: 0.35; margin-top: 1rem; font-weight: 500; letter-spacing: 0.04em; }

/* === PHASE BAR === */
.phase-bar { display: flex; gap: 4px; margin: 1.5rem 0; flex-wrap: wrap; }
.phase-pill {
    padding: 7px 16px; border-radius: 8px; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.02em; transition: all 0.2s; border: 1px solid transparent;
}
.phase-active { background: #0c4a6e; color: #7dd3fc; border-color: rgba(56,189,248,0.3); }
.phase-done { background: #064e3b; color: #6ee7b7; border-color: rgba(16,185,129,0.3); }
.phase-pending { background: #f1f5f9; color: #94a3b8; }

/* === STAT BOXES === */
.stat-row { display: flex; gap: 14px; margin: 1.5rem 0; }
.stat-box {
    flex: 1; background: #ffffff; border: 1px solid #e8ecf1;
    border-radius: 14px; padding: 1.25rem 1rem; text-align: center;
    transition: all 0.15s; position: relative; overflow: hidden;
}
.stat-box::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, #0ea5e9, #10b981); opacity: 0;
    transition: opacity 0.15s;
}
.stat-box:hover::before { opacity: 1; }
.stat-box:hover { border-color: #cbd5e1; }
.stat-box .num { font-size: 1.6rem; font-weight: 700; color: #0f172a; letter-spacing: -0.02em; }
.stat-box .label { font-size: 0.7rem; color: #64748b; margin-top: 4px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }

/* === PATENT CARDS === */
.patent-card {
    border: 1px solid #eaeff5; border-radius: 14px; padding: 1.25rem 1.5rem;
    margin-bottom: 10px; background: #ffffff; transition: all 0.15s;
    position: relative;
}
.patent-card:hover { border-color: #93c5fd; box-shadow: 0 2px 12px rgba(14,165,233,0.06); transform: translateY(-1px); }
.patent-card h4 { font-size: 0.9rem; font-weight: 600; margin: 0 0 0.4rem; color: #0f172a; line-height: 1.4; }
.patent-card .meta { font-size: 0.78rem; color: #64748b; line-height: 1.7; }
.patent-card .applicant {
    display: inline-block; background: #eff6ff; color: #1d4ed8;
    padding: 3px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 600;
    margin-top: 0.5rem; margin-right: 4px; letter-spacing: 0.01em;
}
.relevance {
    display: inline-block; padding: 3px 10px; border-radius: 6px;
    font-size: 0.7rem; font-weight: 600; margin-top: 0.5rem;
}
.rel-high { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
.rel-med { background: #fefce8; color: #854d0e; border: 1px solid #fde68a; }
.rel-low { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

/* === ANALYSIS BOX === */
.analysis-box {
    background: #ffffff; border: 1px solid #e2e8f0; border-left: 4px solid #0ea5e9;
    border-radius: 0 14px 14px 0; padding: 2rem; margin: 1rem 0;
    font-size: 0.88rem; line-height: 1.8; color: #1e293b;
}

/* === HISTORY === */
.history-card { border: 1px solid #eaeff5; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 8px; background: #ffffff; }
.history-card:hover { border-color: #93c5fd; }

/* === BUTTONS === */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0369a1 0%, #0ea5e9 100%) !important;
    color: white !important; border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; letter-spacing: 0.01em !important;
    padding: 0.6rem 1.5rem !important; transition: all 0.15s !important;
    box-shadow: 0 2px 8px rgba(14,165,233,0.2) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 16px rgba(14,165,233,0.3) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]) {
    border-radius: 10px !important; border: 1px solid #e2e8f0 !important;
    font-weight: 500 !important; transition: all 0.15s !important;
}

/* === TABS === */
.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 2px solid #f1f5f9; }
.stTabs [data-baseweb="tab"] {
    font-weight: 500 !important; font-size: 0.82rem !important;
    padding: 10px 20px !important; border-radius: 8px 8px 0 0 !important;
}
.stTabs [aria-selected="true"] {
    background: #f0f9ff !important; color: #0369a1 !important;
    border-bottom: 2px solid #0ea5e9 !important;
}

/* === FILE UPLOADER === */
[data-testid="stFileUploader"] {
    border: 2px dashed #d1d9e6 !important; border-radius: 14px !important;
    background: #f8fafc !important; transition: all 0.15s;
}
[data-testid="stFileUploader"]:hover { border-color: #93c5fd !important; background: #f0f9ff !important; }

/* === TEXT INPUT === */
.stTextInput input {
    border-radius: 10px !important; border: 1px solid #e2e8f0 !important;
    font-size: 0.88rem !important; padding: 0.6rem 0.9rem !important;
}
.stTextInput input:focus { border-color: #0ea5e9 !important; box-shadow: 0 0 0 2px rgba(14,165,233,0.1) !important; }

/* === EXPANDER === */
.streamlit-expanderHeader { font-weight: 500 !important; font-size: 0.88rem !important; border-radius: 10px !important; }

/* === PROGRESS === */
.stProgress > div > div { background: linear-gradient(90deg, #0ea5e9, #10b981) !important; border-radius: 8px !important; }

/* === DIVIDER === */
hr { border-color: #f1f5f9 !important; margin: 1.5rem 0 !important; }

/* === HEADINGS === */
.stMarkdown h3 { font-weight: 600 !important; font-size: 1.15rem !important; color: #0f172a !important; letter-spacing: -0.01em; }

/* === TOAST OVERRIDE === */
[data-testid="stToast"] { border-radius: 10px !important; }

/* === INFO/WARNING BOXES === */
[data-testid="stAlert"] { border-radius: 10px !important; font-size: 0.85rem !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
defaults = {
    "phase": 0, "pdf_text": "", "pdf_name": "",
    "tech_summary": "", "tech_keywords_en": "",
    "search_queries": [],
    "patents_raw": [], "patents_filtered": [],
    "openalex_results": [], "analysis": "", "doc_content": "",
    "page": "main",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Nastavení")
    st.caption("API klíče platí jen pro tuto session.")
    gemini_key = st.text_input("Gemini API Key", value=os.environ.get("GEMINI_API_KEY", ""), type="password", help="https://aistudio.google.com/apikey")
    serpapi_key = st.text_input("SerpApi Key", value=os.environ.get("SERPAPI_KEY", ""), type="password", help="https://serpapi.com")
    st.divider()
    st.markdown("### 📊 Parametry")
    max_patents_per_query = st.slider("Patentů na dotaz", 10, 50, 25)
    max_openalex = st.slider("Max článků z OpenAlex", 5, 50, 30)
    relevance_threshold = st.slider("Min. relevance (0-10)", 0, 10, 5)
    st.divider()
    if st.button("📂 Historie analýz"):
        st.session_state.page = "history"
        st.rerun()
    if st.button("🔬 Nová analýza"):
        st.session_state.page = "main"
        st.rerun()
    st.divider()
    st.caption("AI Transfer System V4.0\nFZÚ AV ČR")

# ---------------------------------------------------------------------------
# CORE: GEMINI WITH RETRY
# ---------------------------------------------------------------------------
def call_gemini(api_key: str, prompt: str, system_instruction: str = "", max_retries: int = 5) -> str:
    """Call Gemini 2.5 Flash with exponential backoff retry on 429/503."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    payload["generationConfig"] = {"temperature": 0.2, "maxOutputTokens": 8192}

    for attempt in range(max_retries):
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise Exception(f"Unexpected response: {json.dumps(data)[:500]}")
        elif resp.status_code in (429, 503):
            wait = (2 ** attempt) + random.uniform(0.5, 1.5)
            st.toast(f"⏳ Gemini přetížen, čekám {wait:.0f}s... (pokus {attempt+1}/{max_retries})")
            time.sleep(wait)
        else:
            raise Exception(f"Gemini error {resp.status_code}: {resp.text[:500]}")

    raise Exception(f"Gemini nedostupný po {max_retries} pokusech. Zkus to znovu za chvíli.")

# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def extract_pdf_text(uploaded_file) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(uploaded_file)
        return "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
    except Exception as e:
        st.error(f"Chyba PDF: {e}")
        return ""

# ---------------------------------------------------------------------------
# STEP 1: ANALYZE DOCUMENT — summary + keywords + queries
# ---------------------------------------------------------------------------
def analyze_document(api_key: str, doc_text: str) -> dict:
    """Extract tech summary, English keywords, and 3 search queries."""
    system = """You are an expert in patent research and technology transfer.

TASK: Based on the technical document, generate:
1. A concise technology summary in Czech (2-3 sentences) — what it is, what makes it unique, what is the principle
2. 5-8 English keywords/keyphrases for searching scientific databases (OpenAlex)
3. THREE different Google Patents search queries from different angles:
   - QUERY 1 (COMPETITORS): Patents on the SAME or SIMILAR technology/method/process
   - QUERY 2 (APPLICATIONS): Patents on PRODUCTS and DEVICES that could USE this technology
   - QUERY 3 (MATERIAL/DOMAIN): Patents on the same material/substance/domain in other contexts

OUTPUT FORMAT (follow exactly):
SUMMARY: [Czech summary]
KEYWORDS: [comma-separated English keywords]
QUERY1: [Google Patents query for competitors]
QUERY2: [Google Patents query for applications]
QUERY3: [Google Patents query for material/domain]

RULES FOR QUERIES:
- Each query max 2-3 phrases connected by AND/OR
- Phrases in quotes, max 3 words per phrase
- In English
- NO markdown, NO explanations, NO numbering beyond the format above

RULES FOR KEYWORDS:
- English only
- Specific to this technology (not generic like "nanotechnology")
- Mix of method keywords and application keywords
- Example: "ZnO nanotetrapod, microwave synthesis, zinc oxide nanostructure, gas sensor, photocatalyst, UV absorption"
"""
    prompt = f"Analyze this document:\n\n{doc_text[:8000]}"
    result = call_gemini(api_key, prompt, system)

    summary = ""
    keywords = ""
    queries = []
    for line in result.strip().split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line[8:].strip()
        elif line.startswith("KEYWORDS:"):
            keywords = line[9:].strip()
        elif line.startswith("QUERY"):
            q = line.split(":", 1)[-1].strip().strip("`").strip('"').strip("'")
            q = re.sub(r"^```.*\n?", "", q)
            q = re.sub(r"\n?```$", "", q)
            if q:
                queries.append(q.strip())

    if not queries:
        queries = [result.strip().strip("`")]

    return {"summary": summary, "keywords": keywords, "queries": queries}

# ---------------------------------------------------------------------------
# STEP 2: SEARCH GOOGLE PATENTS
# ---------------------------------------------------------------------------
def search_google_patents(api_key: str, query: str, max_results: int = 25) -> list:
    url = "https://serpapi.com/search.json"
    patents = []
    page_num = 1
    while len(patents) < max_results:
        params = {"engine": "google_patents", "q": query, "api_key": api_key, "num": min(max_results, 100), "page": page_num}
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"SerpApi error ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        results = data.get("organic_results", [])
        if not results:
            break
        for r in results:
            if len(patents) >= max_results:
                break
            if r.get("is_scholar"):
                continue
            patents.append({
                "title": r.get("title", "—") or "—",
                "abstract": (r.get("snippet", "—") or "—")[:500],
                "applicant": r.get("assignee", "—") or "—",
                "inventor": r.get("inventor", "—") or "—",
                "pub_number": r.get("patent_id", "—") or "—",
                "filing_date": r.get("filing_date", "—") or "—",
                "grant_date": r.get("grant_date", "—") or "—",
                "cpc": r.get("cpc", "—") or "—",
                "pdf_link": r.get("pdf", ""),
                "gp_link": r.get("patent_link", r.get("link", "")),
                "relevance": 0, "rel_type": "—", "rel_reason": "Nefiltrováno",
            })
        if not data.get("serpapi_pagination", {}).get("next"):
            break
        page_num += 1
        time.sleep(0.3)
    return patents

# ---------------------------------------------------------------------------
# STEP 3: AI RELEVANCE FILTER (batched)
# ---------------------------------------------------------------------------
def filter_patents(api_key: str, patents: list, tech_summary: str, threshold: int = 5) -> list:
    if not patents:
        return []

    system = """You are a patent relevance expert. Score each patent's relevance to the given technology.

For EACH patent, return EXACTLY one line:
NUMBER|SCORE|TYPE|REASON

Where:
- NUMBER = patent index number (as listed)
- SCORE = 0-10 (10 = direct competitor/identical technology, 7-9 = highly relevant, 4-6 = partially relevant, 0-3 = irrelevant)
- TYPE = COMPETITOR / PARTNER / CUSTOMER / IRRELEVANT
- REASON = max 10 words why

BE STRICT:
- A patent is COMPETITOR (7-10) only if it describes a similar manufacturing/synthesis method or identical product
- A patent is CUSTOMER (5-7) only if it describes a product/device that could directly use this technology
- A patent is PARTNER (5-7) only if the applicant works in a closely related field
- Everything else is IRRELEVANT (0-3) — this includes patents that share a keyword but are in a completely different domain

OUTPUT: Only lines in NUMBER|SCORE|TYPE|REASON format. Nothing else."""

    BATCH = 15
    scores = {}
    for start in range(0, len(patents), BATCH):
        batch = patents[start:start + BATCH]
        plist = "\n".join(f"{start+i}. {p['title']} | {p['applicant']} | {p['abstract'][:120]}" for i, p in enumerate(batch))
        prompt = f"OUR TECHNOLOGY:\n{tech_summary}\n\nPATENTS TO SCORE:\n{plist}"
        try:
            result = call_gemini(api_key, prompt, system)
            for line in result.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("*"):
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    try:
                        idx = int(parts[0].strip().rstrip("."))
                        score = min(int(parts[1].strip()), 10)
                        rtype = parts[2].strip()
                        reason = parts[3].strip() if len(parts) > 3 else "—"
                        scores[idx] = (score, rtype, reason)
                    except (ValueError, IndexError):
                        continue
        except Exception:
            for i in range(len(batch)):
                scores[start + i] = (3, "—", "Filtr selhal")
        time.sleep(0.5)

    filtered = []
    for i, p in enumerate(patents):
        if i in scores:
            p["relevance"], p["rel_type"], p["rel_reason"] = scores[i]
        else:
            p["relevance"], p["rel_type"], p["rel_reason"] = 2, "—", "Neohodnoceno"
        if p["relevance"] >= threshold:
            filtered.append(p)
    filtered.sort(key=lambda x: x["relevance"], reverse=True)
    return filtered

# ---------------------------------------------------------------------------
# STEP 4: OPENALEX (using English keywords)
# ---------------------------------------------------------------------------
def search_openalex(keywords: str, max_results: int = 30) -> list:
    """Search OpenAlex using English keywords extracted by Gemini."""
    # Clean keywords for search
    query = keywords.strip()
    query = re.sub(r'["\(\)]', '', query)
    # Take first few keywords if too long
    parts = [k.strip() for k in query.split(",")]
    query = " ".join(parts[:5])
    if not query:
        return []

    url = "https://api.openalex.org/works"
    params = {"search": query, "per_page": max_results, "sort": "relevance_score:desc", "mailto": "transfer@fzu.cz"}
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        return []

    results = []
    for work in resp.json().get("results", []):
        institutions = []
        is_commercial = False
        for authorship in work.get("authorships", []):
            for inst in authorship.get("institutions", []):
                name = inst.get("display_name", "")
                itype = inst.get("type", "")
                institutions.append(name)
                if itype in ("company", "facility") or any(t in name.lower() for t in ["inc.", "ltd.", "gmbh", "a.s.", "corp.", "co.", "llc", "ag", "s.r.o."]):
                    is_commercial = True
        results.append({
            "title": work.get("title", "—") or "—", "year": work.get("publication_year", "—"),
            "cited_by": work.get("cited_by_count", 0), "institutions": list(set(institutions))[:5],
            "is_commercial": is_commercial, "doi": work.get("doi", ""), "type": work.get("type", ""),
        })
    return results

# ---------------------------------------------------------------------------
# STEP 5: CRITICAL ANALYSIS
# ---------------------------------------------------------------------------
def run_analysis(api_key: str, tech_summary: str, patents: list, openalex: list, pdf_text: str) -> str:
    system = """You are a CRITICAL technology transfer expert working for a TTO (Technology Transfer Office) at a Czech research institute.

CRITICAL INSTRUCTIONS:
- Be REALISTIC and CRITICAL, not optimistic
- If data does not show clear commercial signals, SAY IT
- Do not suggest companies as partners without concrete evidence in the data
- Distinguish between DIRECT competitors (same technology) and DISTANT players (different field, keyword overlap)
- Ignore patents that have nothing to do with the technology
- For GO/NO-GO be honest — if the technology is too early-stage or the market is small, say it
- Write in CZECH"""

    pat_sum = "\n".join(
        f"- {p['title']} | {p['applicant']} | Relevance: {p.get('relevance','?')}/10 | Type: {p.get('rel_type','?')} | {p.get('rel_reason','')}"
        for p in patents[:20]
    )
    pub_sum = "\n".join(
        f"- {p['title']} ({p['year']}) | Citations: {p['cited_by']} | {', '.join(p['institutions'][:2])}"
        for p in openalex[:15]
    )
    commercial = [r for r in openalex if r["is_commercial"]]
    com_sum = "\n".join(f"- {c['title']} | Companies: {', '.join(c['institutions'][:3])}" for c in commercial) if commercial else "None found."

    prompt = f"""OUR TECHNOLOGY:
{tech_summary}

RELEVANT PATENTS (after AI filtering, sorted by relevance):
{pat_sum}

SCIENTIFIC PUBLICATIONS:
{pub_sum}

PUBLICATIONS WITH COMMERCIAL COLLABORATION:
{com_sum}

SOURCE DOCUMENT EXCERPT:
{pdf_text[:2000]}

Provide a CRITICAL analysis in CZECH:
1. SHRNUTÍ TECHNOLOGIE (2-3 sentences)
2. PATENTOVÁ KRAJINA (who are the REAL competitors — only based on data)
3. KOMERČNÍ SIGNÁLY (what SPECIFICALLY in the data indicates commercial interest — be honest if signals are weak)
4. POTENCIÁLNÍ PARTNEŘI (ONLY companies with concrete evidence in patents or publications)
5. RIZIKA A SLABINY (what could prevent commercialization)
6. GO / CONDITIONAL GO / NO-GO DOPORUČENÍ (with honest reasoning)
7. DOPORUČENÝ DALŠÍ POSTUP (concrete, realistic steps)"""

    return call_gemini(api_key, prompt, system)

# ---------------------------------------------------------------------------
# DOCX EXPORT
# ---------------------------------------------------------------------------
def generate_docx(tech_summary, queries, patents_raw_count, patents, openalex, analysis, pdf_filename, threshold) -> io.BytesIO:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    s = doc.styles["Normal"]; s.font.name = "Calibri"; s.font.size = Pt(10.5); s.paragraph_format.space_after = Pt(6)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("AI Transfer System — Rešeršní zpráva"); r.bold = True; r.font.size = Pt(22); r.font.color.rgb = RGBColor(15, 23, 42)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Zdroj: {pdf_filename}  |  {datetime.now().strftime('%d. %m. %Y %H:%M')}"); r.font.size = Pt(10); r.font.color.rgb = RGBColor(100, 116, 139)
    doc.add_page_break()

    doc.add_heading("1. Shrnutí technologie", level=1)
    doc.add_paragraph(tech_summary)

    doc.add_heading("2. Vyhledávací dotazy", level=1)
    for i, q in enumerate(queries, 1):
        p = doc.add_paragraph(); r = p.add_run(f"Dotaz {i}: "); r.bold = True
        r2 = p.add_run(q); r2.font.name = "Consolas"; r2.font.size = Pt(10); r2.font.color.rgb = RGBColor(3, 105, 161)

    doc.add_heading("3. Nalezené patenty", level=1)
    doc.add_paragraph(f"Celkem: {patents_raw_count} | Po filtraci (práh {threshold}/10): {len(patents)}")
    if patents:
        t = doc.add_table(rows=1, cols=6); t.style = "Light Grid Accent 1"
        for i, h in enumerate(["#", "Název", "Přihlašovatel", "Číslo", "Rel.", "Typ"]):
            c = t.rows[0].cells[i]; c.text = h
            for pg in c.paragraphs:
                for rn in pg.runs: rn.bold = True; rn.font.size = Pt(9)
        for idx, pat in enumerate(patents, 1):
            row = t.add_row().cells
            row[0].text = str(idx); row[1].text = pat["title"][:70]; row[2].text = pat["applicant"][:35]
            row[3].text = pat["pub_number"]; row[4].text = f"{pat.get('relevance','?')}/10"; row[5].text = pat.get("rel_type", "—")
            for c in row:
                for pg in c.paragraphs:
                    for rn in pg.runs: rn.font.size = Pt(8.5)

    doc.add_heading("4. Vědecké publikace (OpenAlex)", level=1)
    doc.add_paragraph(f"Celkem: {len(openalex)} článků")
    commercial = [r for r in openalex if r["is_commercial"]]
    if commercial:
        doc.add_heading("Články s komerční spoluprací:", level=2)
        for r in commercial:
            p = doc.add_paragraph(style="List Bullet")
            rn = p.add_run(f"{r['title']} ({r['year']})"); rn.bold = True; rn.font.size = Pt(9.5)
            p.add_run(f"\n   Instituce: {', '.join(r['institutions'][:3])}")
            p.add_run(f"\n   Citováno: {r['cited_by']}×")

    doc.add_heading("5. AI Analýza komerčního potenciálu", level=1)
    for line in analysis.split("\n"):
        if line.strip(): doc.add_paragraph(line.strip())

    doc.add_page_break()
    doc.add_heading("Metodologie", level=1)
    doc.add_paragraph(f"Systém: AI Transfer System V4.0 | Patenty: Google Patents (SerpApi) | Publikace: OpenAlex | AI: Gemini 2.5 Flash | Filtr: práh {threshold}/10 | Validace: vyžaduje odbornou revizi TTO")
    buf = io.BytesIO(); doc.save(buf); buf.seek(0)
    return buf

# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------
def save_to_history(data: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = re.sub(r'[^\w]', '_', data.get("pdf_name", "unknown"))[:40]
    fname = HISTORY_DIR / f"{ts}_{name}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def load_history() -> list:
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    items = []
    for f in files[:50]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
                d["_filename"] = f.name
                items.append(d)
        except Exception:
            continue
    return items

# ---------------------------------------------------------------------------
# RENDER: PATENT CARD
# ---------------------------------------------------------------------------
def render_patent_card(pat, show_relevance=True):
    applicant_html = f'<span class="applicant">{pat["applicant"]}</span>' if pat["applicant"] != "—" else ""
    links = ""
    if pat.get("gp_link"):
        links += f'<a href="{pat["gp_link"]}" target="_blank" style="font-size:0.75rem;color:#0ea5e9;text-decoration:none;">↗ Google Patents</a>'
    rel_html = ""
    if show_relevance:
        sc = pat.get("relevance", 0)
        cls = "rel-high" if sc >= 7 else ("rel-med" if sc >= 5 else "rel-low")
        rel_html = f'<span class="relevance {cls}">{sc}/10 · {pat.get("rel_type","—")}</span>'
        reason = pat.get("rel_reason", "")
        if reason and reason != "Nefiltrováno":
            rel_html += f'<div class="meta" style="margin-top:4px;font-style:italic;">{reason}</div>'
    st.markdown(f"""<div class="patent-card">
        <h4>{pat['title']}</h4>
        <div class="meta">{pat['abstract'][:250]}{'...' if len(pat['abstract'])>250 else ''}</div>
        <div class="meta" style="margin-top:8px;"><strong>Č.:</strong> {pat['pub_number']} · <strong>Podáno:</strong> {pat['filing_date']} · {links}</div>
        {applicant_html} {rel_html}
    </div>""", unsafe_allow_html=True)


# ===========================================================================
# PAGE: HISTORY
# ===========================================================================
if st.session_state.page == "history":
    st.markdown("""<div class="hero">
        <div class="hero-badge">Archiv</div>
        <h1>Historie analýz</h1>
        <p>Přehled všech dosavadních rešerší a jejich výsledků</p>
    </div>""", unsafe_allow_html=True)

    items = load_history()
    if not items:
        st.info("Zatím žádné uložené analýzy. Spusť první rešerši.")
    else:
        for item in items:
            ts = item.get("timestamp", "—")
            name = item.get("pdf_name", "—")
            summary = item.get("tech_summary", "—")[:150]
            n_pat = len(item.get("patents_filtered", []))
            n_pub = len(item.get("openalex_results", []))
            with st.expander(f"📄 {name}  —  {ts}  ({n_pat} patentů, {n_pub} publikací)"):
                st.markdown(f"**Shrnutí:** {item.get('tech_summary', '—')}")
                st.markdown(f"**Dotazy:** {', '.join(item.get('search_queries', []))}")
                if item.get("analysis"):
                    st.markdown(f'<div class="analysis-box">{item["analysis"][:2000]}...</div>', unsafe_allow_html=True)
    st.stop()


# ===========================================================================
# PAGE: MAIN ANALYSIS
# ===========================================================================
st.markdown("""<div class="hero">
    <div class="hero-badge">Patent & Research Intelligence</div>
    <h1>AI Transfer System</h1>
    <p>Automatizovaná rešerše patentů a vědeckých publikací pro hodnocení komerčního potenciálu vynálezů</p>
    <div class="hero-org">Fyzikální ústav AV ČR — Transfer znalostí a technologií</div>
</div>""", unsafe_allow_html=True)

phases = [("Upload PDF", 0), ("AI analýza dokumentu", 1), ("Rešerše", 2), ("AI filtr", 3), ("Analýza", 4), ("Export", 5)]
phase_html = '<div class="phase-bar">'
for label, idx in phases:
    cls = "phase-done" if idx < st.session_state.phase else ("phase-active" if idx == st.session_state.phase else "phase-pending")
    phase_html += f'<span class="phase-pill {cls}">{label}</span>'
st.markdown(phase_html + "</div>", unsafe_allow_html=True)

# --- PHASE 0: Upload ---
st.markdown("### 📄 Nahraj technický dokument")
uploaded = st.file_uploader("PDF patent, výzkumná zpráva, prezentace technologie", type=["pdf"])

if uploaded and not st.session_state.pdf_text:
    with st.spinner("Extrahuji text z PDF..."):
        text = extract_pdf_text(uploaded)
        if text:
            st.session_state.pdf_text = text
            st.session_state.pdf_name = uploaded.name
            st.session_state.phase = 1
            st.rerun()
        else:
            st.error("Nepodařilo se extrahovat text.")

if st.session_state.pdf_text:
    with st.expander("📋 Extrahovaný text", expanded=False):
        st.text(st.session_state.pdf_text[:3000] + ("..." if len(st.session_state.pdf_text) > 3000 else ""))

# --- PHASE 1: Document analysis ---
if st.session_state.phase >= 1 and not st.session_state.search_queries:
    st.markdown("---")
    st.markdown("### 🧠 AI analýza dokumentu")
    st.caption("Gemini vytvoří shrnutí, klíčová slova a 3 cílené vyhledávací dotazy")
    if not gemini_key:
        st.warning("Zadej Gemini API klíč v bočním panelu.")
    elif st.button("🚀 Analyzovat dokument", type="primary"):
        with st.spinner("Gemini analyzuje dokument... (při přetížení se automaticky zopakuje)"):
            try:
                result = analyze_document(gemini_key, st.session_state.pdf_text)
                st.session_state.tech_summary = result["summary"]
                st.session_state.tech_keywords_en = result["keywords"]
                st.session_state.search_queries = result["queries"]
                st.session_state.phase = 2
                st.rerun()
            except Exception as e:
                st.error(f"Chyba: {e}")

if st.session_state.search_queries:
    st.markdown("---")
    st.markdown("### 🔍 Výsledek AI analýzy dokumentu")
    if st.session_state.tech_summary:
        st.info(f"**Shrnutí:** {st.session_state.tech_summary}")
    if st.session_state.tech_keywords_en:
        st.caption(f"**Klíčová slova (EN):** {st.session_state.tech_keywords_en}")
    updated = []
    labels = ["🎯 Konkurence", "📱 Aplikace", "🧪 Materiál/Doména"]
    for i, q in enumerate(st.session_state.search_queries):
        lbl = labels[i] if i < len(labels) else f"Dotaz {i+1}"
        edited = st.text_input(lbl, value=q, key=f"q_{i}")
        updated.append(edited)
    st.session_state.search_queries = updated

# --- PHASE 2+3: Search + Filter ---
if st.session_state.phase >= 2 and st.session_state.search_queries and not st.session_state.patents_filtered:
    st.markdown("---")
    can_search = bool(serpapi_key)
    if not can_search:
        st.warning("Zadej SerpApi Key v bočním panelu.")
    if st.button("🔎 Spustit rešerši + AI filtr relevance", type="primary", disabled=not can_search):
        all_patents = []; seen = set()
        total_q = len(st.session_state.search_queries)
        progress = st.progress(0, text="Spouštím rešerši...")

        for qi, query in enumerate(st.session_state.search_queries):
            progress.progress(int((qi / total_q) * 35), text=f"Dotaz {qi+1}/{total_q}: {query[:50]}...")
            try:
                results = search_google_patents(serpapi_key, query, max_patents_per_query)
                for p in results:
                    pid = p["pub_number"]
                    if pid not in seen:
                        seen.add(pid); p["source_query"] = query; all_patents.append(p)
            except Exception as e:
                st.warning(f"Dotaz {qi+1} selhal: {e}")
            time.sleep(0.3)

        st.session_state.patents_raw = all_patents
        progress.progress(40, text=f"{len(all_patents)} patentů nalezeno. AI filtr relevance...")

        if gemini_key and all_patents:
            try:
                filtered = filter_patents(gemini_key, all_patents, st.session_state.tech_summary, relevance_threshold)
                st.session_state.patents_filtered = filtered
                progress.progress(70, text=f"{len(filtered)} relevantních. Hledám publikace...")
            except Exception as e:
                st.warning(f"AI filtr: {e}")
                st.session_state.patents_filtered = all_patents
        else:
            st.session_state.patents_filtered = all_patents

        # OpenAlex — use English keywords
        progress.progress(75, text="Hledám vědecké publikace (OpenAlex)...")
        try:
            openalex = search_openalex(st.session_state.tech_keywords_en, max_openalex)
            st.session_state.openalex_results = openalex
        except Exception as e:
            st.warning(f"OpenAlex: {e}")

        progress.progress(100, text="Hotovo!")
        time.sleep(0.3); progress.empty()
        st.session_state.phase = 4; st.rerun()

# --- Display results ---
if st.session_state.patents_raw:
    st.markdown("---")
    st.markdown("### 📊 Výsledky rešerše")

    raw_c = len(st.session_state.patents_raw)
    filt_c = len(st.session_state.patents_filtered)
    competitors = [p for p in st.session_state.patents_filtered if "KOMPET" in p.get("rel_type", "").upper() or "COMPETITOR" in p.get("rel_type", "").upper()]
    commercial = [r for r in st.session_state.openalex_results if r["is_commercial"]]
    unique_app = list(set(p["applicant"] for p in st.session_state.patents_filtered if p["applicant"] != "—"))

    st.markdown(f"""<div class="stat-row">
        <div class="stat-box"><div class="num">{raw_c} → {filt_c}</div><div class="label">Patentů (před/po filtraci)</div></div>
        <div class="stat-box"><div class="num">{len(competitors)}</div><div class="label">Konkurentů</div></div>
        <div class="stat-box"><div class="num">{len(st.session_state.openalex_results)}</div><div class="label">Publikací</div></div>
        <div class="stat-box"><div class="num">{len(commercial)}</div><div class="label">Komerční spolupráce</div></div>
    </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["✅ Relevantní patenty", "📋 Všechny patenty (nefiltrované)", "📚 Publikace (OpenAlex)"])

    with tab1:
        if not st.session_state.patents_filtered:
            st.info("Žádné patenty neprošly filtrem relevance. Zkus snížit práh v bočním panelu.")
        for pat in st.session_state.patents_filtered:
            render_patent_card(pat, show_relevance=True)

    with tab2:
        st.caption(f"Všech {raw_c} patentů ze všech dotazů — včetně vyřazených filtrem")
        for pat in st.session_state.patents_raw:
            render_patent_card(pat, show_relevance=True)

    with tab3:
        if not st.session_state.openalex_results:
            st.info("Žádné publikace nenalezeny.")
        for pub in st.session_state.openalex_results:
            badge = "🏢 " if pub["is_commercial"] else ""
            insts = ", ".join(pub["institutions"][:3]) if pub["institutions"] else "—"
            st.markdown(f"""<div class="patent-card">
                <h4>{badge}{pub['title']}</h4>
                <div class="meta"><strong>Rok:</strong> {pub['year']} · <strong>Citováno:</strong> {pub['cited_by']}× · <strong>Typ:</strong> {pub['type']}</div>
                <div class="meta" style="margin-top:4px;"><strong>Instituce:</strong> {insts}</div>
            </div>""", unsafe_allow_html=True)

# --- PHASE 4: Analysis ---
if st.session_state.phase >= 4 and st.session_state.patents_filtered and not st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 🤖 Kritická AI analýza komerčního potenciálu")
    if not gemini_key:
        st.warning("Zadej Gemini API klíč.")
    elif st.button("🧪 Spustit kritickou analýzu", type="primary"):
        with st.spinner("Gemini provádí kritickou analýzu... (automatický retry při přetížení)"):
            try:
                analysis = run_analysis(gemini_key, st.session_state.tech_summary, st.session_state.patents_filtered, st.session_state.openalex_results, st.session_state.pdf_text)
                st.session_state.analysis = analysis
                st.session_state.phase = 5

                # Auto-save to history
                save_to_history({
                    "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "pdf_name": st.session_state.pdf_name,
                    "tech_summary": st.session_state.tech_summary,
                    "tech_keywords_en": st.session_state.tech_keywords_en,
                    "search_queries": st.session_state.search_queries,
                    "patents_raw_count": len(st.session_state.patents_raw),
                    "patents_filtered": [{"title": p["title"], "applicant": p["applicant"], "pub_number": p["pub_number"], "relevance": p["relevance"], "rel_type": p["rel_type"], "rel_reason": p["rel_reason"]} for p in st.session_state.patents_filtered],
                    "openalex_results": [{"title": p["title"], "year": p["year"], "cited_by": p["cited_by"], "is_commercial": p["is_commercial"], "institutions": p["institutions"]} for p in st.session_state.openalex_results],
                    "analysis": analysis,
                })

                st.rerun()
            except Exception as e:
                st.error(f"Chyba: {e}")

if st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 🤖 Výsledek kritické AI analýzy")
    st.markdown(f'<div class="analysis-box">{st.session_state.analysis}</div>', unsafe_allow_html=True)

# --- PHASE 5: Export ---
if st.session_state.phase >= 5 and st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 📥 Export zprávy")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Vygenerovat Word dokument", type="primary"):
            with st.spinner("Generuji .docx..."):
                try:
                    buf = generate_docx(
                        st.session_state.tech_summary, st.session_state.search_queries,
                        len(st.session_state.patents_raw), st.session_state.patents_filtered,
                        st.session_state.openalex_results, st.session_state.analysis,
                        st.session_state.pdf_name, relevance_threshold,
                    )
                    st.session_state.doc_content = buf.getvalue()
                    st.success("Dokument vygenerován!")
                except Exception as e:
                    st.error(f"Chyba: {e}")
    if st.session_state.doc_content:
        with col2:
            st.download_button("⬇️ Stáhnout .docx", data=st.session_state.doc_content,
                file_name=f"reserse_{datetime.now().strftime('%Y%m%d_%H%M')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

if st.session_state.phase > 0:
    st.markdown("---")
    if st.button("🔄 Nová analýza (reset)"):
        for k in defaults: st.session_state[k] = defaults[k]
        st.rerun()

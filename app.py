"""
AI Transfer System V6.1 — FZÚ Patent & Research Intelligence
=============================================================
Game-changer edition:
- Prompt sets from prompt_sets/*.toml
- Clean FZÚ-inspired UX/UI
- Patent jurisdictions + estimated patent families
- Commercial Readiness Score / decision engine
- Evidence-based GO / CONDITIONAL GO / NO-GO
- Manual text input + PDF input
- Cached Google Patents and OpenAlex calls
- DOCX/XLSX exports with scorecard, patent families and next steps

Pipeline: PDF/Text → Gemini → Google Patents → AI filtr → OpenAlex → Families → Scorecard → Analysis → Docs + Excel
"""

import streamlit as st
import requests
import json
import time
import os
import io
import re
import random
import math
from datetime import datetime
from pathlib import Path
from collections import Counter

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python <= 3.10


# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Transfer System — FZÚ",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

HISTORY_DIR = Path("analysis_history")
HISTORY_DIR.mkdir(exist_ok=True)
PROMPT_ROOT = Path("prompt_sets")


# ---------------------------------------------------------------------------
# DEFAULT PROMPTS
# ---------------------------------------------------------------------------
DEFAULT_PROMPTS = {
    "analyze_document": {
        "system": """You are an expert in patent research, market analysis and technology transfer.

TASK: Based on the technical document, generate:
1. A concise technology summary in Czech (2-3 sentences)
2. A LIST of ALL potential application domains mentioned or implied in the document (in English)
3. 5-8 English keywords/keyphrases for searching scientific databases
4. FIVE different Google Patents search queries — each targeting a DIFFERENT application domain or angle:
   - QUERY 1 (CORE TECHNOLOGY): The exact technology/method/synthesis described
   - QUERY 2 (APPLICATION 1): First application domain (e.g. electronics, sensors)
   - QUERY 3 (APPLICATION 2): Second application domain (e.g. biomedicine, coatings)
   - QUERY 4 (APPLICATION 3): Third application domain (e.g. energy, catalysis, optics)
   - QUERY 5 (MATERIAL): The base material in broader contexts
5. Identify likely value proposition and possible substitute technologies.

CRITICAL RULES:
- Cover ALL application areas, not just one
- Do NOT focus on just one property or application
- Each patent query max 2-3 phrases with AND/OR, in English
- NO markdown, NO explanations

OUTPUT FORMAT (follow exactly):
SUMMARY: [Czech summary]
DOMAINS: [comma-separated English application domains]
KEYWORDS: [comma-separated English keywords]
VALUE_PROPOSITION: [Czech value proposition in one sentence]
SUBSTITUTES: [comma-separated English alternatives/substitutes]
QUERY1: [core technology query]
QUERY2: [application 1 query]
QUERY3: [application 2 query]
QUERY4: [application 3 query]
QUERY5: [material query]""",
        "user": """Analyze this document thoroughly. Identify ALL applications, commercial use cases, possible substitutes and search angles:

{{doc_text}}""",
    },
    "filter_patents": {
        "system": """You are a patent relevance and commercial landscape expert. Score each patent vs the given technology.
For EACH patent return one line: NUMBER|SCORE|TYPE|REASON
- SCORE 0-10 (10=identical technology, 7-9=very relevant, 4-6=partial, 0-3=weak/irrelevant)
- TYPE = COMPETITOR/PARTNER/CUSTOMER/SUBSTITUTE/IRRELEVANT
- REASON = max 12 words

EVALUATION CRITERIA:
- Compare the patent ABSTRACT with the technology description
- COMPETITOR: similar method, material, device, or direct technical alternative
- CUSTOMER: product/device/company that could use the technology as input
- PARTNER: complementary capability or adjacent R&D direction
- SUBSTITUTE: different technology solving the same market problem
- IRRELEVANT: keyword overlap only or different domain

BE STRICT. Only NUMBER|SCORE|TYPE|REASON lines.""",
        "user": """TECHNOLOGY:
{{tech_summary}}

PATENTS:
{{patent_list}}""",
    },
    "final_analysis": {
        "system": """You are a critical technology transfer expert at a Czech TTO.
Write in Czech. Be realistic, evidence-based and commercially useful.
Do not use markdown formatting. Do not use **, ##, *, or backticks.
Do not invent partners or market evidence. If evidence is weak, say it clearly.
Use the scorecard and evidence tables as decision support, not as absolute truth.
Your goal is to help management decide whether to continue, pause, or redirect the technology transfer effort.""",
        "user": """TECHNOLOGIE:
{{tech_summary}}

DECISION SCORECARD:
{{scorecard_context}}

TOP PŘIHLAŠOVATELÉ PATENTŮ:
{{assignee_table}}

VÝVOJ PATENTOVÉ AKTIVITY PO LETECH:
{{yearly_table}}

PATENTOVÉ RODINY A GEOGRAFICKÉ POKRYTÍ:
{{family_table}}

GEOGRAFICKÉ ROZLOŽENÍ PODLE KÓDŮ:
{{country_table}}

RELEVANTNÍ PATENTY:
{{patent_summary}}

PUBLIKACE:
{{publication_summary}}

KOMERČNÍ SPOLUPRÁCE V PUBLIKACÍCH:
{{commercial_summary}}

ZDROJOVÝ DOKUMENT:
{{source_document}}

Proveď kritickou analýzu v češtině v této struktuře:

1. EXECUTIVE SUMMARY
- Technologie jednou větou
- Komerční příležitost jednou větou
- Doporučení jednou větou

2. HODNOTOVÁ NABÍDKA
- Jaký problém technologie řeší
- Pro koho by to mohlo mít hodnotu
- Čím je potenciálně lepší než současné řešení

3. PATENTOVÁ A KONKURENČNÍ KRAJINA
- Hlavní hráči
- Patentové rodiny a geografické pokrytí
- Co naznačuje patentová aktivita

4. TRŽNÍ A PARTNERSKÉ SIGNÁLY
- Kde jsou nejsilnější signály
- Kde jsou slabé nebo chybějící signály
- Kteří partneři dávají smysl pouze podle dostupných dat

5. RIZIKA A DEVIL'S ADVOCATE
- Technologická rizika
- Tržní rizika
- Patentová / konkurenční rizika
- Co by mohlo způsobit, že komercializace nebude dávat smysl

6. VERDIKT
- GO / CONDITIONAL GO / NO-GO
- Vysvětli proč
- Uveď míru jistoty: Low / Medium / High

7. DALŠÍ KROKY NA 1-3 MĚSÍCE
- Konkrétní validace
- Koho oslovit
- Jaká data doplnit
- Co musí být splněno pro posun dál""",
    },
}


# ---------------------------------------------------------------------------
# PROMPT LOADER
# ---------------------------------------------------------------------------
def get_available_prompt_sets():
    sets = []
    if PROMPT_ROOT.exists():
        sets = sorted([p.stem for p in PROMPT_ROOT.glob("*.toml")])
    if "default" not in sets:
        sets.insert(0, "default")
    return sets or ["default"]


@st.cache_data(show_spinner=False)
def load_prompt_config(prompt_set):
    prompt_path = PROMPT_ROOT / f"{prompt_set}.toml"
    if not prompt_path.exists():
        return DEFAULT_PROMPTS

    with open(prompt_path, "rb") as f:
        parsed = tomllib.load(f)

    merged = json.loads(json.dumps(DEFAULT_PROMPTS))
    for section, values in parsed.items():
        if section not in merged:
            merged[section] = {}
        if isinstance(values, dict):
            merged[section].update(values)
    return merged


def get_prompt(prompt_set, section):
    config = load_prompt_config(prompt_set)
    if section not in config:
        raise KeyError(f"V prompt sadě chybí sekce: {section}")
    system_prompt = config[section].get("system", "").strip()
    user_prompt = config[section].get("user", "").strip()
    if not system_prompt or not user_prompt:
        raise ValueError(f"Prompt sekce {section} musí obsahovat položky system a user.")
    return system_prompt, user_prompt


def render_prompt(template, **kwargs):
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def get_secret_or_env(name, default=""):
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return value or os.environ.get(name, default)


# ---------------------------------------------------------------------------
# CLEAN FZÚ-INSPIRED CSS / UI — V6.1
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --bg: #f6f8fb;
  --panel: #ffffff;
  --ink: #101828;
  --muted: #667085;
  --line: #e4e7ec;
  --navy: #071122;
  --blue: #1455d9;
  --cyan: #00a3ff;
  --green: #17b26a;
  --red: #f04438;
  --yellow: #f79009;
  --shadow: 0 14px 36px rgba(16, 24, 40, 0.07);
}

html, body, [class*="st-"] {
  font-family: 'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

html, body, .stApp { background: var(--bg) !important; color: var(--ink); }
.block-container { max-width: 1180px; padding: 1.5rem 1.4rem 4rem; }
#MainMenu, footer { visibility: hidden; }

/* Sidebar: čisté, ne sci-fi */
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid var(--line) !important;
}
[data-testid="stSidebar"] * { color: var(--ink) !important; }
[data-testid="stSidebar"] h3 {
  font-size: .78rem !important;
  letter-spacing: .06em !important;
  text-transform: uppercase !important;
  color: #344054 !important;
  margin-top: .6rem !important;
}
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small, [data-testid="stSidebar"] p {
  color: var(--muted) !important;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {
  background: #ffffff !important;
  border: 1px solid #d0d5dd !important;
  border-radius: 12px !important;
  color: var(--ink) !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] button {
  background: #ffffff !important;
  border: 1px solid #d0d5dd !important;
  border-radius: 12px !important;
  color: var(--ink) !important;
  font-weight: 700 !important;
}
[data-testid="stSidebar"] button:hover {
  border-color: var(--blue) !important;
  background: #f5f8ff !important;
}

/* Main hero */
.hero {
  background: var(--panel);
  color: var(--ink);
  padding: 1.55rem 1.65rem;
  border-radius: 22px;
  margin-bottom: 1rem;
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
}
.hero:before {
  content: "";
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 6px;
  background: linear-gradient(180deg, var(--blue), var(--cyan), var(--green));
}
.hero-grid {
  display: grid;
  grid-template-columns: 1.2fr .8fr;
  gap: 22px;
  align-items: center;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #175cd3;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  padding: 5px 11px;
  border-radius: 999px;
  font-size: .72rem;
  font-weight: 800;
  letter-spacing: .05em;
  text-transform: uppercase;
  margin-bottom: .8rem;
}
.hero h1 {
  font-size: clamp(2rem, 3vw, 3rem);
  line-height: 1;
  font-weight: 800;
  margin: 0 0 .65rem;
  letter-spacing: -.055em;
  color: var(--navy);
}
.hero p {
  font-size: .98rem;
  line-height: 1.55;
  color: #475467;
  margin: 0;
  max-width: 760px;
}
.hero-org {
  font-size: .78rem;
  color: #667085;
  margin-top: .9rem;
  font-weight: 700;
}
.hero-chip-row { display: flex; gap: 7px; flex-wrap: wrap; margin-top: .9rem; }
.hero-chip {
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid #e4e7ec;
  font-size: .72rem;
  font-weight: 700;
  color: #344054;
}
.hero-panel {
  background: #f8fafc;
  border: 1px solid #e4e7ec;
  border-radius: 18px;
  padding: 1.05rem;
}
.hero-panel .big { font-size: 2rem; font-weight: 800; letter-spacing: -.045em; color: var(--navy); }
.hero-panel .small { font-size: .72rem; color: #667085; font-weight: 800; text-transform: uppercase; letter-spacing: .07em; }

/* Phase navigation */
.phase-bar { display: flex; gap: 8px; margin: .85rem 0 1.35rem; flex-wrap: wrap; }
.phase-pill {
  padding: 7px 13px;
  border-radius: 999px;
  font-size: .73rem;
  font-weight: 800;
  border: 1px solid var(--line);
  background: #ffffff;
  color: #667085;
}
.phase-active { background: var(--navy); color: #fff; border-color: var(--navy); }
.phase-done { background: #ecfdf3; color: #067647; border-color: #abefc6; }
.phase-pending { background: #fff; color: #98a2b3; }

/* Cards */
.fzu-card, [data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 18px !important;
}
.metric-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 1rem 0; }
.metric-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: .9rem 1rem;
  box-shadow: 0 8px 24px rgba(16,24,40,.045);
}
.metric-card .num { font-size: 1.45rem; font-weight: 800; color: var(--navy); letter-spacing: -.04em; }
.metric-card .label { font-size: .66rem; color: var(--muted); margin-top: 2px; font-weight: 800; text-transform: uppercase; letter-spacing: .07em; }

/* Scorecard */
.score-grid { display: grid; grid-template-columns: .72fr 1.28fr; gap: 14px; margin: 1rem 0 1.25rem; }
.score-ring {
  min-height: 230px;
  border-radius: 20px;
  background: var(--navy);
  color: #fff;
  padding: 1.15rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: 0 14px 34px rgba(7,17,34,.18);
}
.score-number { font-size: 4rem; font-weight: 800; line-height: .95; letter-spacing: -.075em; }
.score-verdict { display: inline-flex; width: fit-content; padding: 7px 11px; border-radius: 999px; font-size: .72rem; font-weight: 900; letter-spacing: .07em; text-transform: uppercase; }
.verdict-go { background: rgba(23,178,106,.16); color: #86efac; border: 1px solid rgba(23,178,106,.36); }
.verdict-conditional { background: rgba(247,144,9,.16); color: #fedf89; border: 1px solid rgba(247,144,9,.36); }
.verdict-no { background: rgba(240,68,56,.16); color: #fda29b; border: 1px solid rgba(240,68,56,.36); }
.score-table { background: #fff; border: 1px solid var(--line); border-radius: 20px; padding: 1rem; box-shadow: 0 8px 24px rgba(16,24,40,.045); }
.score-row { display: grid; grid-template-columns: 170px 1fr 42px; gap: 12px; align-items: center; margin: 8px 0; }
.score-label { font-size: .78rem; color: #344054; font-weight: 800; }
.score-track { height: 8px; background: #eef2f6; border-radius: 999px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--blue), var(--cyan), var(--green)); }
.score-val { font-family: 'JetBrains Mono'; font-size: .74rem; color: var(--navy); font-weight: 800; text-align: right; }

/* Data cards */
.patent-card {
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem 1.1rem;
  margin-bottom: 10px;
  background: #fff;
  box-shadow: 0 7px 20px rgba(16,24,40,.04);
}
.patent-card:hover { border-color: #93c5fd; box-shadow: 0 10px 26px rgba(20,85,217,.075); }
.patent-card h4 { font-size: .93rem; font-weight: 800; margin: 0 0 .4rem; color: var(--navy); }
.patent-card .meta { font-size: .78rem; color: #667085; line-height: 1.65; }
.patent-card .applicant { display: inline-block; background: #eff6ff; color: #175cd3; padding: 4px 10px; border-radius: 999px; font-size: .7rem; font-weight: 800; margin-top: .55rem; margin-right: 4px; }
.relevance { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: .7rem; font-weight: 900; margin-top: .55rem; }
.rel-high { background: #ecfdf3; color: #067647; border: 1px solid #abefc6; }
.rel-med { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }
.rel-low { background: #fef3f2; color: #b42318; border: 1px solid #fecdca; }
.analysis-box { background: #fff; border: 1px solid var(--line); border-left: 5px solid var(--blue); border-radius: 0 18px 18px 0; padding: 1.5rem; margin: 1rem 0; font-size: .9rem; line-height: 1.78; white-space: pre-wrap; box-shadow: 0 8px 24px rgba(16,24,40,.045); }

/* Streamlit controls */
.stButton > button[kind="primary"] {
  background: var(--navy) !important;
  color: white !important;
  border: none !important;
  border-radius: 12px !important;
  font-weight: 800 !important;
  box-shadow: 0 8px 22px rgba(7,17,34,.15);
}
.stButton > button[kind="primary"]:hover { background: #12233f !important; }
.stTabs [aria-selected="true"] { background: #eff6ff !important; color: #175cd3 !important; border-radius: 999px !important; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
[data-testid="stFileUploader"] { background: transparent !important; }
[data-testid="stFileUploaderDropzone"] {
  background: #ffffff !important;
  border: 1px dashed #b8c7d9 !important;
  border-radius: 16px !important;
  min-height: 90px !important;
  padding: 1rem !important;
}
[data-testid="stFileUploaderDropzone"] button {
  background: var(--navy) !important;
  color: #ffffff !important;
  border-radius: 10px !important;
  border: none !important;
  font-weight: 800 !important;
}
textarea, input { border-radius: 12px !important; }

@media (max-width: 980px) {
  .hero-grid, .score-grid, .metric-grid { grid-template-columns: 1fr; }
  .score-row { grid-template-columns: 1fr; gap: 4px; }
  .hero { padding: 1.25rem; }
}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------------------
defaults = {
    "phase": 0,
    "pdf_text": "",
    "pdf_name": "",
    "tech_summary": "",
    "tech_keywords_en": "",
    "tech_domains": "",
    "value_proposition": "",
    "substitutes": "",
    "search_queries": [],
    "patents_raw": [],
    "patents_filtered": [],
    "openalex_results": [],
    "scorecard": {},
    "analysis": "",
    "doc_content": b"",
    "xlsx_content": b"",
    "page": "main",
    "active_prompt_set": "default",
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

    gemini_key = st.text_input("Gemini API Key", value=get_secret_or_env("GEMINI_API_KEY"), type="password")
    serpapi_key = st.text_input("SerpApi Key", value=get_secret_or_env("SERPAPI_KEY"), type="password")

    st.divider()
    st.markdown("### 🧠 Prompty")
    prompt_set = st.selectbox(
        "Prompt sada",
        get_available_prompt_sets(),
        index=0,
        help="Každý soubor prompt_sets/*.toml se zobrazí jako samostatná prompt sada.",
    )
    prompt_file = PROMPT_ROOT / f"{prompt_set}.toml"
    if prompt_file.exists():
        st.caption(f"Používám: `{prompt_file}`")
    else:
        st.caption("Používám vestavěné default prompty.")

    if st.session_state.phase > 0 and st.session_state.active_prompt_set != prompt_set:
        st.warning("Prompt sada byla změněna. Pro čistý výsledek spusť novou analýzu od začátku.")
        if st.button("🔄 Resetovat a použít novou prompt sadu"):
            for k in defaults:
                st.session_state[k] = defaults[k]
            st.session_state.active_prompt_set = prompt_set
            st.rerun()
    elif st.session_state.phase == 0:
        st.session_state.active_prompt_set = prompt_set

    with st.expander("Náhled aktivních promptů", expanded=False):
        try:
            for section_name in ["analyze_document", "filter_patents", "final_analysis"]:
                system_p, user_p = get_prompt(prompt_set, section_name)
                st.markdown(f"**{section_name}**")
                st.caption(f"System: {system_p[:220]}...")
                st.caption(f"User: {user_p[:220]}...")
        except Exception as e:
            st.warning(str(e))

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
        for k in defaults:
            st.session_state[k] = defaults[k]
        st.session_state.active_prompt_set = prompt_set
        st.session_state.page = "main"
        st.rerun()

    st.divider()
    st.caption("AI Transfer System V6.1\nFZÚ AV ČR")


# ---------------------------------------------------------------------------
# GEMINI
# ---------------------------------------------------------------------------
def call_gemini(api_key, prompt, system_instruction="", max_retries=5):
    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash"]
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        payload["generationConfig"] = {"temperature": 0.2, "maxOutputTokens": 8192}

        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                if resp.status_code in (429, 503):
                    wait = (2 ** attempt) * 2 + random.uniform(1, 3)
                    if attempt < max_retries - 1:
                        st.toast(f"⏳ {model} přetížen, čekám {wait:.0f}s...")
                        time.sleep(wait)
                    else:
                        break
                else:
                    raise Exception(f"Gemini {resp.status_code}: {resp.text[:300]}")
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    break
        st.toast(f"⚠️ {model} nedostupný, zkouším další...")
        time.sleep(2)
    raise Exception("Všechny Gemini modely jsou přetížené nebo nedostupné. Zkus to za chvíli znovu.")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
PATENT_JURISDICTIONS = {
    "US": "United States", "EP": "European Patent Office", "WO": "WIPO / PCT", "CN": "China",
    "JP": "Japan", "KR": "South Korea", "DE": "Germany", "GB": "United Kingdom", "FR": "France",
    "CA": "Canada", "AU": "Australia", "IN": "India", "CZ": "Czech Republic", "SK": "Slovakia",
    "PL": "Poland", "NL": "Netherlands", "IT": "Italy", "ES": "Spain", "SE": "Sweden", "FI": "Finland",
    "DK": "Denmark", "NO": "Norway", "CH": "Switzerland", "AT": "Austria", "BE": "Belgium",
    "RU": "Russia", "BR": "Brazil", "MX": "Mexico", "IL": "Israel", "SG": "Singapore", "TW": "Taiwan",
    "HK": "Hong Kong", "EA": "Eurasian Patent Organization", "OA": "OAPI", "AP": "ARIPO",
}


def extract_pdf_text(f):
    import PyPDF2
    reader = PyPDF2.PdfReader(f)
    pages = []
    for p in reader.pages:
        text = p.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


def extract_country(patent_id):
    if not patent_id or patent_id == "—":
        return "—"
    clean = re.sub(r"[^A-Za-z0-9]", "", str(patent_id)).upper()
    m = re.match(r"^([A-Z]{2})", clean)
    return m.group(1) if m else "—"


def get_jurisdiction_name(code):
    if not code or code == "—":
        return "—"
    return PATENT_JURISDICTIONS.get(code, code)


def parse_patent_code(patent_id):
    if not patent_id or patent_id == "—":
        return {"jurisdiction": "—", "jurisdiction_name": "—", "numeric_part": "—", "kind_code": "—", "normalized_pub": "—"}
    clean = re.sub(r"[^A-Za-z0-9]", "", str(patent_id)).upper()
    m = re.match(r"^([A-Z]{2})([0-9]+)([A-Z][0-9]?)?$", clean)
    if not m:
        jurisdiction = extract_country(clean)
        return {"jurisdiction": jurisdiction, "jurisdiction_name": get_jurisdiction_name(jurisdiction), "numeric_part": "—", "kind_code": "—", "normalized_pub": clean}
    jurisdiction, numeric_part, kind_code = m.groups()
    kind_code = kind_code or "—"
    suffix = "" if kind_code == "—" else kind_code
    return {"jurisdiction": jurisdiction, "jurisdiction_name": get_jurisdiction_name(jurisdiction), "numeric_part": numeric_part, "kind_code": kind_code, "normalized_pub": f"{jurisdiction}{numeric_part}{suffix}"}


def normalize_text_key(value, max_len=80):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r" +", " ", value).strip()
    return value[:max_len]


def estimate_family_key(patent):
    title_key = normalize_text_key(patent.get("title", ""), 100)
    applicant_key = normalize_text_key(patent.get("applicant", ""), 60)
    if title_key and applicant_key:
        return f"{applicant_key} | {title_key}"
    if title_key:
        return title_key
    code = parse_patent_code(patent.get("pub_number", ""))
    return f"{code['jurisdiction']}|{code['numeric_part']}"


def extract_year(date_str):
    if not date_str or date_str == "—":
        return None
    m = re.search(r"(\d{4})", str(date_str))
    return int(m.group(1)) if m else None


def strip_markdown(text):
    if not text:
        return ""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    return text


def clamp(value, lo=0, hi=10):
    return max(lo, min(hi, value))


def compute_stats(patents):
    assignees = [p.get("applicant", "—") for p in patents if p.get("applicant", "—") != "—"]
    assignee_counts = Counter(assignees).most_common(20)

    years = [extract_year(p.get("filing_date", "—")) for p in patents]
    years = [y for y in years if y and 2000 <= y <= 2030]
    year_counts = Counter(years)
    if year_counts:
        year_range = range(min(year_counts.keys()), max(year_counts.keys()) + 1)
        yearly = [(y, year_counts.get(y, 0)) for y in year_range]
    else:
        yearly = []

    countries = [p.get("country") or extract_country(p.get("pub_number", "")) for p in patents]
    country_counts = Counter(c for c in countries if c and c != "—").most_common(20)

    rel_types = Counter([str(p.get("rel_type", "—")).upper() for p in patents])

    family_map = {}
    for p in patents:
        family_key = p.get("family_key") or estimate_family_key(p)
        code = p.get("country") or extract_country(p.get("pub_number", ""))
        if family_key not in family_map:
            family_map[family_key] = {
                "family_key": family_key,
                "title": p.get("title", "—"),
                "applicant": p.get("applicant", "—"),
                "patent_count": 0,
                "countries": set(),
                "country_names": set(),
                "publication_numbers": [],
                "best_relevance": 0,
            }
        family_map[family_key]["patent_count"] += 1
        if code and code != "—":
            family_map[family_key]["countries"].add(code)
            family_map[family_key]["country_names"].add(get_jurisdiction_name(code))
        if p.get("pub_number"):
            family_map[family_key]["publication_numbers"].append(p.get("pub_number"))
        family_map[family_key]["best_relevance"] = max(family_map[family_key]["best_relevance"], int(p.get("relevance", 0) or 0))

    families = []
    for item in family_map.values():
        countries_sorted = sorted(item["countries"])
        names_sorted = sorted(item["country_names"])
        families.append({
            "family_key": item["family_key"],
            "title": item["title"],
            "applicant": item["applicant"],
            "patent_count": item["patent_count"],
            "country_count": len(countries_sorted),
            "countries": ", ".join(countries_sorted) if countries_sorted else "—",
            "country_names": ", ".join(names_sorted) if names_sorted else "—",
            "publication_numbers": ", ".join(item["publication_numbers"][:12]),
            "best_relevance": item["best_relevance"],
        })
    families.sort(key=lambda x: (x["country_count"], x["patent_count"], x["best_relevance"]), reverse=True)

    return {"assignees": assignee_counts, "yearly": yearly, "countries": country_counts, "families": families, "rel_types": rel_types}


def compute_trend_score(yearly):
    nonzero = [(y, c) for y, c in yearly if c > 0]
    if len(nonzero) < 3:
        return 4
    recent = sum(c for y, c in nonzero if y >= max(y for y, _ in nonzero) - 2)
    older = sum(c for y, c in nonzero if y < max(y for y, _ in nonzero) - 2)
    if recent == 0:
        return 2
    ratio = recent / max(older, 1)
    return clamp(3 + ratio * 2.2)


def compute_decision_score(filtered_patents, raw_patents, openalex, stats):
    patents_for_score = filtered_patents or raw_patents[:20]
    relevances = [int(p.get("relevance", 0) or 0) for p in patents_for_score]
    avg_top_relevance = sum(sorted(relevances, reverse=True)[:10]) / max(len(sorted(relevances, reverse=True)[:10]), 1)

    rel_types = stats.get("rel_types", Counter())
    competitor_count = sum(v for k, v in rel_types.items() if "COMPET" in k or "SUBSTITUTE" in k)
    partner_count = sum(v for k, v in rel_types.items() if "PARTNER" in k or "CUSTOMER" in k)
    commercial_pub_count = len([r for r in openalex if r.get("is_commercial")])
    unique_assignees = len(stats.get("assignees", []))
    families = stats.get("families", [])
    countries = stats.get("countries", [])
    multi_country_families = len([f for f in families if f.get("country_count", 0) >= 2])

    technical_fit = clamp(avg_top_relevance)
    market_pull = clamp(2.5 + partner_count * 0.8 + commercial_pub_count * 1.0 + min(len(openalex), 30) / 10)
    patent_strength = clamp(math.log1p(len(raw_patents)) * 2.6 + compute_trend_score(stats.get("yearly", [])) * 0.35)
    family_geo_strength = clamp(len(countries) * 1.15 + multi_country_families * 1.5 + min(len(families), 20) * 0.12)
    partner_availability = clamp(unique_assignees * 0.45 + partner_count * 1.1 + commercial_pub_count * 0.9)
    risk_manageability = clamp(8.5 - competitor_count * 0.55 + partner_count * 0.18 - max(0, 5 - len(raw_patents)) * 0.5)
    evidence_confidence = clamp(2.5 + min(len(raw_patents), 60) / 9 + min(len(openalex), 40) / 12 + len(countries) * 0.35)

    dimensions = {
        "Technical fit": round(technical_fit, 1),
        "Market pull": round(market_pull, 1),
        "Patent strength": round(patent_strength, 1),
        "Family / geography": round(family_geo_strength, 1),
        "Partner availability": round(partner_availability, 1),
        "Risk manageability": round(risk_manageability, 1),
        "Evidence confidence": round(evidence_confidence, 1),
    }

    weights = {
        "Technical fit": 0.18,
        "Market pull": 0.17,
        "Patent strength": 0.15,
        "Family / geography": 0.14,
        "Partner availability": 0.14,
        "Risk manageability": 0.12,
        "Evidence confidence": 0.10,
    }
    weighted_10 = sum(dimensions[k] * weights[k] for k in dimensions)
    score_100 = int(round(weighted_10 * 10))

    if score_100 >= 70 and dimensions["Risk manageability"] >= 4.5:
        verdict = "GO"
    elif score_100 >= 45:
        verdict = "CONDITIONAL GO"
    else:
        verdict = "NO-GO"

    confidence = "High" if dimensions["Evidence confidence"] >= 7.2 else ("Medium" if dimensions["Evidence confidence"] >= 4.8 else "Low")

    risk_flags = []
    if dimensions["Market pull"] < 4.5:
        risk_flags.append("Slabé tržní/partnerské signály")
    if dimensions["Family / geography"] < 4:
        risk_flags.append("Nízké geografické pokrytí patentů")
    if dimensions["Risk manageability"] < 5:
        risk_flags.append("Vyšší konkurenční nebo substituční riziko")
    if dimensions["Evidence confidence"] < 5:
        risk_flags.append("Nízká datová jistota")
    if not risk_flags:
        risk_flags.append("Bez zásadní červené vlajky v dostupných datech")

    evidence = [
        f"{len(raw_patents)} nalezených patentových záznamů, {len(filtered_patents)} po AI filtraci relevance",
        f"{len(families)} odhadovaných patentových rodin, {len(countries)} států/úřadů",
        f"{commercial_pub_count} publikací s komerční afiliací podle OpenAlex heuristiky",
        f"{unique_assignees} unikátních přihlašovatelů ve filtrovaném setu",
    ]

    next_steps = []
    if dimensions["Market pull"] < 6:
        next_steps.append("Ověřit market pull: oslovit 5-8 firem v nejsilnější aplikační doméně a zjistit bolest, budget a aktuální řešení.")
    if dimensions["Family / geography"] < 6:
        next_steps.append("Doplnit přesnější patent-family data: priority, family members a právní stav pro US/EP/WO/CN/JP.")
    if dimensions["Risk manageability"] < 6:
        next_steps.append("Udělat rychlý FTO/risk screening na top konkurenční a substituční patentové rodiny.")
    if dimensions["Technical fit"] >= 7:
        next_steps.append("Připravit one-page non-confidential technology brief pro první partnerské oslovení.")
    if not next_steps:
        next_steps.append("Pokračovat validací partnerů a doplnit ekonomický model s konzervativním licenčním scénářem.")

    return {
        "score_100": score_100,
        "verdict": verdict,
        "confidence": confidence,
        "dimensions": dimensions,
        "risk_flags": risk_flags,
        "evidence": evidence,
        "next_steps": next_steps,
        "weights": weights,
    }


def scorecard_to_text(scorecard):
    if not scorecard:
        return "Scorecard není k dispozici."
    lines = [
        f"Celkové skóre: {scorecard.get('score_100', '—')}/100",
        f"Verdikt: {scorecard.get('verdict', '—')}",
        f"Míra jistoty: {scorecard.get('confidence', '—')}",
        "Dílčí skóre:",
    ]
    for k, v in scorecard.get("dimensions", {}).items():
        lines.append(f"- {k}: {v}/10")
    lines.append("Rizika:")
    for r in scorecard.get("risk_flags", []):
        lines.append(f"- {r}")
    lines.append("Doporučené validace:")
    for s in scorecard.get("next_steps", []):
        lines.append(f"- {s}")
    return "\n".join(lines)


def verdict_class(verdict):
    if verdict == "GO":
        return "verdict-go"
    if verdict == "CONDITIONAL GO":
        return "verdict-conditional"
    return "verdict-no"


def render_score_dashboard(scorecard):
    if not scorecard:
        return
    dimensions = scorecard.get("dimensions", {})
    rows = ""
    for label, value in dimensions.items():
        pct = max(0, min(100, float(value) * 10))
        rows += f"""
        <div class="score-row">
          <div class="score-label">{label}</div>
          <div class="score-track"><div class="score-fill" style="width:{pct:.0f}%"></div></div>
          <div class="score-val">{value}/10</div>
        </div>
        """
    st.markdown(
        f"""
        <div class="score-grid">
          <div class="score-ring">
            <div>
              <div class="score-verdict {verdict_class(scorecard.get('verdict'))}">{scorecard.get('verdict')}</div>
              <div style="height:20px"></div>
              <div class="score-number">{scorecard.get('score_100')}</div>
              <div style="font-weight:800; opacity:.75; letter-spacing:.05em; text-transform:uppercase;">Commercial Readiness Score</div>
            </div>
            <div style="font-size:.82rem; opacity:.72; line-height:1.5;">
              Confidence: <strong>{scorecard.get('confidence')}</strong><br>
              Skóre je heuristika pro screening, ne právní ani investiční posudek.
            </div>
          </div>
          <div class="score-table">
            <div style="font-weight:900; font-size:1.05rem; margin-bottom:.7rem;">Decision engine</div>
            {rows}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# AI STEPS
# ---------------------------------------------------------------------------
def analyze_document(api_key, doc_text, prompt_set="default"):
    system, user_template = get_prompt(prompt_set, "analyze_document")
    prompt = render_prompt(user_template, doc_text=doc_text[:9000])
    result = call_gemini(api_key, prompt, system)

    summary, keywords, domains, value_prop, substitutes, queries = "", "", "", "", "", []
    for line in result.strip().split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            summary = line[8:].strip()
        elif line.startswith("KEYWORDS:"):
            keywords = line[9:].strip()
        elif line.startswith("DOMAINS:"):
            domains = line[8:].strip()
        elif line.startswith("VALUE_PROPOSITION:"):
            value_prop = line.split(":", 1)[1].strip()
        elif line.startswith("SUBSTITUTES:"):
            substitutes = line.split(":", 1)[1].strip()
        elif line.startswith("QUERY"):
            q = line.split(":", 1)[-1].strip().strip("`\"'")
            q = re.sub(r"^```.*\n?", "", q)
            q = re.sub(r"\n?```$", "", q)
            if q:
                queries.append(q.strip())

    return {
        "summary": summary or "—",
        "keywords": keywords or "—",
        "domains": domains or "—",
        "value_proposition": value_prop or "—",
        "substitutes": substitutes or "—",
        "queries": queries or [result.strip()],
    }


@st.cache_data(ttl=86400, show_spinner=False)
def search_google_patents(api_key, query, max_results=25):
    patents, page_num = [], 1
    while len(patents) < max_results:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_patents", "q": query, "api_key": api_key, "num": 100, "page": page_num},
            timeout=30,
        )
        if resp.status_code != 200:
            raise Exception(f"SerpApi {resp.status_code}: {resp.text[:250]}")
        data = resp.json()
        for r in data.get("organic_results", []):
            if len(patents) >= max_results:
                break
            if r.get("is_scholar"):
                continue
            pid = r.get("patent_id", "—") or "—"
            parsed = parse_patent_code(pid)
            pat = {
                "title": r.get("title", "—") or "—",
                "abstract": (r.get("snippet", "—") or "—")[:600],
                "applicant": r.get("assignee", "—") or "—",
                "inventor": r.get("inventor", "—") or "—",
                "pub_number": pid,
                "filing_date": r.get("filing_date", "—") or "—",
                "grant_date": r.get("grant_date", "—") or "—",
                "country": parsed["jurisdiction"],
                "jurisdiction_name": parsed["jurisdiction_name"],
                "kind_code": parsed["kind_code"],
                "normalized_pub": parsed["normalized_pub"],
                "cpc": r.get("cpc", "—") or "—",
                "pdf_link": r.get("pdf", ""),
                "gp_link": r.get("patent_link", r.get("link", "")),
                "relevance": 0,
                "rel_type": "—",
                "rel_reason": "Nefiltrováno",
            }
            pat["family_key"] = estimate_family_key(pat)
            patents.append(pat)
        if not data.get("organic_results") or not data.get("serpapi_pagination", {}).get("next"):
            break
        page_num += 1
        time.sleep(0.3)
    return patents


def filter_patents(api_key, patents, tech_summary, threshold=5, prompt_set="default"):
    if not patents:
        return []
    system, user_template = get_prompt(prompt_set, "filter_patents")
    batch_size, scores = 15, {}

    for start in range(0, len(patents), batch_size):
        batch = patents[start:start + batch_size]
        plist = "\n".join(
            f"{start + i}. {p.get('title', '—')} | {p.get('applicant', '—')} | {p.get('abstract', '—')[:170]}"
            for i, p in enumerate(batch)
        )
        prompt = render_prompt(user_template, tech_summary=tech_summary, patent_list=plist)
        try:
            result = call_gemini(api_key, prompt, system)
            for line in result.strip().split("\n"):
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    try:
                        idx = int(parts[0].strip().rstrip("."))
                        score = min(max(int(parts[1].strip()), 0), 10)
                        rel_type = parts[2].strip()
                        reason = parts[3].strip() if len(parts) > 3 else "—"
                        scores[idx] = (score, rel_type, reason)
                    except Exception:
                        pass
        except Exception as e:
            st.warning(f"AI filtr selhal pro batch {start // batch_size + 1}: {e}")
        time.sleep(0.5)

    filtered = []
    for i, p in enumerate(patents):
        if i in scores:
            p["relevance"], p["rel_type"], p["rel_reason"] = scores[i]
        else:
            p["relevance"], p["rel_type"], p["rel_reason"] = 2, "—", "Neohodnoceno"
        if p["relevance"] >= threshold:
            filtered.append(p)
    filtered.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return filtered


@st.cache_data(ttl=86400, show_spinner=False)
def search_openalex(keywords, max_results=30):
    query = re.sub(r'["\(\)]', "", keywords.strip())
    parts = [k.strip() for k in query.split(",")][:5]
    query = " ".join(parts)
    if not query:
        return []
    resp = requests.get(
        "https://api.openalex.org/works",
        params={"search": query, "per_page": max_results, "sort": "relevance_score:desc", "mailto": "transfer@fzu.cz"},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    results = []
    for w in resp.json().get("results", []):
        insts, is_com = [], False
        for a in w.get("authorships", []):
            for inst in a.get("institutions", []):
                n = inst.get("display_name", "")
                if n:
                    insts.append(n)
                if inst.get("type") in ("company", "facility") or any(t in n.lower() for t in ["inc.", "ltd.", "gmbh", "a.s.", "corp.", "co.", "llc", "ag"]):
                    is_com = True
        results.append({
            "title": w.get("title", "—") or "—",
            "year": w.get("publication_year", "—"),
            "cited_by": w.get("cited_by_count", 0),
            "institutions": list(set(insts))[:5],
            "is_commercial": is_com,
            "doi": w.get("doi", ""),
            "type": w.get("type", ""),
        })
    return results


def run_analysis(api_key, tech_summary, patents, openalex, pdf_text, stats, scorecard, prompt_set="default"):
    system, user_template = get_prompt(prompt_set, "final_analysis")

    assignee_table = "\n".join(f"  {name}: {count} patentů" for name, count in stats.get("assignees", [])[:10]) or "Žádná data."
    yearly_str = "\n".join(f"  {y}: {c} patentů" for y, c in stats.get("yearly", []) if c > 0) or "Žádná data."
    pat_sum = "\n".join(
        f"- {p.get('title', '—')} | {p.get('applicant', '—')} | {p.get('relevance', '?')}/10 | {p.get('rel_type', '?')} | {p.get('rel_reason', '')} | {p.get('country', '—')}"
        for p in patents[:20]
    ) or "Žádné relevantní patenty."
    pub_sum = "\n".join(
        f"- {p.get('title', '—')} ({p.get('year', '—')}) | Citací: {p.get('cited_by', 0)} | {', '.join(p.get('institutions', [])[:2])}"
        for p in openalex[:15]
    ) or "Žádné publikace."
    commercial = [r for r in openalex if r.get("is_commercial")]
    com_sum = "\n".join(f"- {c.get('title', '—')} | {', '.join(c.get('institutions', [])[:3])}" for c in commercial) if commercial else "Žádné."
    family_sum = "\n".join(
        f"- {f.get('title', '—')} | {f.get('applicant', '—')} | {f.get('patent_count', 0)} záznamů | {f.get('country_count', 0)} států/úřadů | {f.get('countries', '—')}"
        for f in stats.get("families", [])[:15]
    ) or "Žádné odhadované rodiny."
    country_sum = "\n".join(f"- {code} ({get_jurisdiction_name(code)}): {count} záznamů" for code, count in stats.get("countries", [])[:20]) or "Žádná data."

    prompt = render_prompt(
        user_template,
        tech_summary=tech_summary,
        scorecard_context=scorecard_to_text(scorecard),
        assignee_table=assignee_table,
        yearly_table=yearly_str,
        patent_summary=pat_sum,
        publication_summary=pub_sum,
        commercial_summary=com_sum,
        family_table=family_sum,
        country_table=country_sum,
        source_document=pdf_text[:2200],
    )
    return call_gemini(api_key, prompt, system)


# ---------------------------------------------------------------------------
# EXPORTS
# ---------------------------------------------------------------------------
def generate_xlsx(patents, openalex, tech_summary, scorecard):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    hfont = Font(bold=True, size=10, color="FFFFFF")
    hfill = PatternFill(start_color="071122", end_color="071122", fill_type="solid")
    thin = Side(style="thin", color="D1D9E6")
    border = Border(bottom=thin)

    ws0 = wb.active
    ws0.title = "Scorecard"
    ws0.cell(row=1, column=1, value="Commercial Readiness Score").font = Font(bold=True, size=16)
    ws0.cell(row=2, column=1, value="Skóre")
    ws0.cell(row=2, column=2, value=scorecard.get("score_100", "—"))
    ws0.cell(row=3, column=1, value="Verdikt")
    ws0.cell(row=3, column=2, value=scorecard.get("verdict", "—"))
    ws0.cell(row=4, column=1, value="Confidence")
    ws0.cell(row=4, column=2, value=scorecard.get("confidence", "—"))
    row = 6
    ws0.cell(row=row, column=1, value="Dimenze").font = Font(bold=True)
    ws0.cell(row=row, column=2, value="Skóre 0-10").font = Font(bold=True)
    for k, v in scorecard.get("dimensions", {}).items():
        row += 1
        ws0.cell(row=row, column=1, value=k)
        ws0.cell(row=row, column=2, value=v)
    row += 2
    ws0.cell(row=row, column=1, value="Rizika").font = Font(bold=True)
    for item in scorecard.get("risk_flags", []):
        row += 1
        ws0.cell(row=row, column=1, value=item)
    row += 2
    ws0.cell(row=row, column=1, value="Další kroky").font = Font(bold=True)
    for item in scorecard.get("next_steps", []):
        row += 1
        ws0.cell(row=row, column=1, value=item)
    ws0.column_dimensions["A"].width = 55
    ws0.column_dimensions["B"].width = 18

    ws = wb.create_sheet("Patenty")
    headers = ["#", "Název", "Vynálezce", "Majitel", "Datum podání", "Kód", "Stát / patentový úřad", "Číslo patentu", "Kind code", "Odhad rodiny", "CPC", "Relevance", "Typ", "Důvod relevance", "Abstrakt", "Odkaz"]
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hfont
        c.fill = hfill
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for idx, p in enumerate(patents, 1):
        r = idx + 1
        country_code = p.get("country", extract_country(p.get("pub_number", "")))
        values = [idx, p.get("title", "—"), p.get("inventor", "—"), p.get("applicant", "—"), p.get("filing_date", "—"), country_code, p.get("jurisdiction_name", get_jurisdiction_name(country_code)), p.get("pub_number", "—"), p.get("kind_code", parse_patent_code(p.get("pub_number", ""))["kind_code"]), p.get("family_key", estimate_family_key(p))[:120], p.get("cpc", "—"), p.get("relevance", 0), p.get("rel_type", "—"), p.get("rel_reason", "—"), p.get("abstract", "—"), p.get("gp_link", "")]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.font = Font(size=9)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = border
    for col, width in {"A": 4, "B": 42, "C": 25, "D": 25, "E": 12, "F": 8, "G": 24, "H": 18, "I": 10, "J": 35, "K": 20, "L": 8, "M": 14, "N": 26, "O": 50, "P": 30}.items():
        ws.column_dimensions[col].width = width
    ws.auto_filter.ref = ws.dimensions

    ws2 = wb.create_sheet("Publikace")
    pub_headers = ["#", "Název", "Rok", "Citací", "Komerční", "Instituce", "Typ", "DOI"]
    for col, h in enumerate(pub_headers, 1):
        c = ws2.cell(row=1, column=col, value=h)
        c.font = hfont
        c.fill = hfill
    for idx, p in enumerate(openalex, 1):
        values = [idx, p.get("title", "—"), p.get("year", "—"), p.get("cited_by", 0), "Ano" if p.get("is_commercial") else "Ne", ", ".join(p.get("institutions", [])[:4]), p.get("type", ""), p.get("doi", "")]
        for col, value in enumerate(values, 1):
            ws2.cell(row=idx + 1, column=col, value=value)
    ws2.column_dimensions["B"].width = 50
    ws2.column_dimensions["F"].width = 40
    ws2.auto_filter.ref = ws2.dimensions

    stats = compute_stats(patents)
    ws3 = wb.create_sheet("Statistiky")
    ws3.cell(row=1, column=1, value="Top přihlašovatelé patentů").font = Font(bold=True, size=12)
    ws3.cell(row=2, column=1, value="Firma/Instituce").font = Font(bold=True)
    ws3.cell(row=2, column=2, value="Počet patentů").font = Font(bold=True)
    for i, (name, count) in enumerate(stats["assignees"], 3):
        ws3.cell(row=i, column=1, value=name)
        ws3.cell(row=i, column=2, value=count)
    ws3.column_dimensions["A"].width = 42
    ws3.column_dimensions["B"].width = 18

    row_start = len(stats["assignees"]) + 5
    ws3.cell(row=row_start, column=1, value="Patentová aktivita po letech").font = Font(bold=True, size=12)
    ws3.cell(row=row_start + 1, column=1, value="Rok").font = Font(bold=True)
    ws3.cell(row=row_start + 1, column=2, value="Počet patentů").font = Font(bold=True)
    for i, (year, count) in enumerate(stats["yearly"], row_start + 2):
        ws3.cell(row=i, column=1, value=year)
        ws3.cell(row=i, column=2, value=count)

    row_start_2 = row_start + len(stats["yearly"]) + 5
    ws3.cell(row=row_start_2, column=1, value="Geografické rozložení").font = Font(bold=True, size=12)
    ws3.cell(row=row_start_2 + 1, column=1, value="Kód").font = Font(bold=True)
    ws3.cell(row=row_start_2 + 1, column=2, value="Stát / úřad").font = Font(bold=True)
    ws3.cell(row=row_start_2 + 1, column=3, value="Počet").font = Font(bold=True)
    for i, (country, count) in enumerate(stats["countries"], row_start_2 + 2):
        ws3.cell(row=i, column=1, value=country)
        ws3.cell(row=i, column=2, value=get_jurisdiction_name(country))
        ws3.cell(row=i, column=3, value=count)

    ws4 = wb.create_sheet("Patentové rodiny")
    fam_headers = ["#", "Název", "Majitel", "Počet záznamů", "Počet států/úřadů", "Kódy", "Státy/úřady", "Publikační čísla", "Nejvyšší relevance"]
    for col, h in enumerate(fam_headers, 1):
        c = ws4.cell(row=1, column=col, value=h)
        c.font = hfont
        c.fill = hfill
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    for idx, fam in enumerate(stats.get("families", []), 1):
        values = [idx, fam.get("title", "—"), fam.get("applicant", "—"), fam.get("patent_count", 0), fam.get("country_count", 0), fam.get("countries", "—"), fam.get("country_names", "—"), fam.get("publication_numbers", "—"), fam.get("best_relevance", 0)]
        for col, value in enumerate(values, 1):
            ws4.cell(row=idx + 1, column=col, value=value)
    ws4.column_dimensions["B"].width = 45
    ws4.column_dimensions["C"].width = 28
    ws4.column_dimensions["G"].width = 40
    ws4.column_dimensions["H"].width = 45
    ws4.auto_filter.ref = ws4.dimensions

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def generate_docx(tech_summary, queries, patents_raw_count, patents, openalex, analysis, pdf_filename, threshold, stats, scorecard, prompt_set="default"):
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    s = doc.styles["Normal"]
    s.font.name = "Calibri"
    s.font.size = Pt(10.5)
    s.paragraph_format.space_after = Pt(6)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("AI Transfer System — Rešeršní zpráva")
    r.bold = True
    r.font.size = Pt(22)
    r.font.color.rgb = RGBColor(7, 17, 34)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"Zdroj: {pdf_filename}  |  {datetime.now().strftime('%d. %m. %Y %H:%M')}")
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(100, 116, 139)
    doc.add_page_break()

    doc.add_heading("1. Decision scorecard", level=1)
    doc.add_paragraph(f"Commercial Readiness Score: {scorecard.get('score_100', '—')}/100")
    doc.add_paragraph(f"Verdikt: {scorecard.get('verdict', '—')}")
    doc.add_paragraph(f"Míra jistoty: {scorecard.get('confidence', '—')}")
    t = doc.add_table(rows=1, cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text = "Dimenze"
    t.rows[0].cells[1].text = "Skóre 0-10"
    for k, v in scorecard.get("dimensions", {}).items():
        row = t.add_row().cells
        row[0].text = k
        row[1].text = str(v)

    doc.add_heading("2. Shrnutí technologie", level=1)
    doc.add_paragraph(strip_markdown(tech_summary))

    doc.add_heading("3. Vyhledávací dotazy", level=1)
    for i, q in enumerate(queries, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"Dotaz {i}: ")
        r.bold = True
        r2 = p.add_run(q)
        r2.font.name = "Consolas"
        r2.font.size = Pt(10)
        r2.font.color.rgb = RGBColor(3, 105, 161)

    doc.add_heading("4. Přehled přihlašovatelů patentů", level=1)
    doc.add_paragraph(f"Celkem nalezeno {patents_raw_count} patentů, po filtraci/exportu: {len(patents)}")
    if stats.get("assignees"):
        t = doc.add_table(rows=1, cols=3)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["#", "Firma / Instituce", "Počet patentů"]):
            t.rows[0].cells[i].text = h
        for idx, (name, count) in enumerate(stats["assignees"][:15], 1):
            row = t.add_row().cells
            row[0].text = str(idx)
            row[1].text = name
            row[2].text = str(count)

    doc.add_heading("5. Patentové rodiny a geografické pokrytí", level=1)
    if stats.get("families"):
        t = doc.add_table(rows=1, cols=6)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["#", "Název", "Majitel", "Záznamů", "Států/úřadů", "Kódy"]):
            t.rows[0].cells[i].text = h
        for idx, fam in enumerate(stats.get("families", [])[:15], 1):
            row = t.add_row().cells
            row[0].text = str(idx)
            row[1].text = fam.get("title", "—")[:55]
            row[2].text = fam.get("applicant", "—")[:30]
            row[3].text = str(fam.get("patent_count", 0))
            row[4].text = str(fam.get("country_count", 0))
            row[5].text = fam.get("countries", "—")

    doc.add_heading("6. Tabulka patentů", level=1)
    if patents:
        t = doc.add_table(rows=1, cols=8)
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(["#", "Název", "Majitel", "Vynálezce", "Kód", "Stát/úřad", "Datum", "Rel."]):
            t.rows[0].cells[i].text = h
        for idx, pat in enumerate(patents[:30], 1):
            row = t.add_row().cells
            country_code = pat.get("country", "—")
            row[0].text = str(idx)
            row[1].text = pat.get("title", "—")[:60]
            row[2].text = pat.get("applicant", "—")[:30]
            row[3].text = pat.get("inventor", "—")[:30]
            row[4].text = country_code
            row[5].text = pat.get("jurisdiction_name", get_jurisdiction_name(country_code))[:25]
            row[6].text = pat.get("filing_date", "—")
            row[7].text = f"{pat.get('relevance', '?')}/10"

    doc.add_heading("7. Vědecké publikace (OpenAlex)", level=1)
    doc.add_paragraph(f"Celkem: {len(openalex)} článků")
    commercial = [r for r in openalex if r.get("is_commercial")]
    if commercial:
        doc.add_heading("Články s komerční spoluprací:", level=2)
        for r in commercial[:10]:
            p = doc.add_paragraph(style="List Bullet")
            rn = p.add_run(f"{r.get('title', '—')} ({r.get('year', '—')})")
            rn.bold = True
            p.add_run(f"\n   Instituce: {', '.join(r.get('institutions', [])[:3])}")

    doc.add_heading("8. AI Analýza komerčního potenciálu", level=1)
    clean_analysis = strip_markdown(analysis)
    for line in clean_analysis.split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\d+\.", line) or line.endswith(":"):
            p = doc.add_paragraph()
            r = p.add_run(line)
            r.bold = True
            r.font.size = Pt(11)
        else:
            doc.add_paragraph(line)

    doc.add_page_break()
    doc.add_heading("Metodologie a nastavení", level=1)
    doc.add_paragraph("Systém: AI Transfer System V6.1")
    doc.add_paragraph(f"Datum: {datetime.now().strftime('%d. %m. %Y %H:%M')}")
    doc.add_paragraph(f"Zdrojový dokument: {pdf_filename}")
    doc.add_paragraph(f"Prompt sada: {prompt_set}")
    doc.add_paragraph("Patentová databáze: Google Patents (via SerpApi)")
    doc.add_paragraph("Vědecké publikace: OpenAlex")
    doc.add_paragraph(f"Práh relevance: {threshold}/10")
    doc.add_paragraph("Výsledky vyžadují odbornou validaci pracovníkem TTO. Scorecard je screeningová heuristika, ne právní stanovisko.")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# HISTORY
# ---------------------------------------------------------------------------
def save_to_history(data):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = re.sub(r"[^\w]", "_", data.get("pdf_name", "unknown"))[:40]
    with open(HISTORY_DIR / f"{ts}_{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def load_history():
    items = []
    for f in sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:50]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                items.append(json.load(fh))
        except Exception:
            pass
    return items


def render_patent_card(pat, show_relevance=True):
    app_html = f'<span class="applicant">{pat.get("applicant", "—")}</span>' if pat.get("applicant", "—") != "—" else ""
    link = f'<a href="{pat.get("gp_link", "")}" target="_blank" style="font-size:0.75rem;color:#1177ff;text-decoration:none;font-weight:800;">↗ Google Patents</a>' if pat.get("gp_link") else ""
    rel_html = ""
    if show_relevance and pat.get("relevance", 0) > 0:
        sc = pat.get("relevance", 0)
        cls = "rel-high" if sc >= 7 else ("rel-med" if sc >= 5 else "rel-low")
        rel_html = f'<span class="relevance {cls}">{sc}/10 · {pat.get("rel_type", "—")}</span>'
        if pat.get("rel_reason", "") not in ("", "—", "Nefiltrováno"):
            rel_html += f'<div class="meta" style="margin-top:4px;font-style:italic;">{pat.get("rel_reason", "")}</div>'
    st.markdown(
        f"""<div class="patent-card">
        <h4>{pat.get('title', '—')}</h4>
        <div class="meta">{pat.get('abstract', '—')[:280]}{'...' if len(pat.get('abstract', '')) > 280 else ''}</div>
        <div class="meta" style="margin-top:8px;"><strong>Č.:</strong> {pat.get('pub_number', '—')} · <strong>Stát/úřad:</strong> {pat.get('country', '—')} ({pat.get('jurisdiction_name', get_jurisdiction_name(pat.get('country', '—')))}) · <strong>Rodina:</strong> {str(pat.get('family_key', '—'))[:45]} · <strong>Podáno:</strong> {pat.get('filing_date', '—')} · {link}</div>
        {app_html} {rel_html}
    </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# HISTORY PAGE
# ---------------------------------------------------------------------------
if st.session_state.page == "history":
    st.markdown("""<div class="hero"><div class="hero-badge">Archiv</div><h1>Historie analýz</h1><p>Přehled dosavadních rešerší a scorecard výsledků.</p></div>""", unsafe_allow_html=True)
    history = load_history()
    if history:
        import pandas as pd
        rows = []
        for item in history:
            sc = item.get("scorecard", {})
            rows.append({
                "Datum": item.get("timestamp", "—"),
                "Dokument": item.get("pdf_name", "—"),
                "Prompt": item.get("prompt_set", "—"),
                "Skóre": sc.get("score_100", "—"),
                "Verdikt": sc.get("verdict", "—"),
                "Confidence": sc.get("confidence", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    for item in history:
        sc = item.get("scorecard", {})
        with st.expander(f"📄 {item.get('pdf_name', '—')} — {item.get('timestamp', '—')} — {sc.get('score_100', '—')}/100 {sc.get('verdict', '')}"):
            st.caption(f"Prompt sada: {item.get('prompt_set', '—')}")
            st.markdown(f"**Shrnutí:** {item.get('tech_summary', '—')}")
            if item.get("analysis"):
                st.markdown(f'<div class="analysis-box">{item["analysis"][:2200]}...</div>', unsafe_allow_html=True)
    if not history:
        st.info("Žádné uložené analýzy.")
    st.stop()


# ---------------------------------------------------------------------------
# MAIN PAGE
# ---------------------------------------------------------------------------
st.markdown(
    """
<div class="hero">
  <div class="hero-grid">
    <div>
      <div class="hero-badge">Patent & Research Intelligence</div>
      <h1>AI Transfer System</h1>
      <p>Screening komerčního potenciálu technologií pro TTO: patenty, publikace, patentové rodiny, geografické pokrytí a rozhodovací scorecard.</p>
      <div class="hero-chip-row">
        <span class="hero-chip">Patent families</span>
        <span class="hero-chip">Commercial score</span>
        <span class="hero-chip">Evidence report</span>
      </div>
      <div class="hero-org">Fyzikální ústav AV ČR — Transfer znalostí a technologií</div>
    </div>
    <div class="hero-panel">
      <div class="small">Aktuální režim</div>
      <div class="big">V6.1</div>
      <div style="color:#667085; font-size:.86rem; line-height:1.55; margin-top:.35rem;">Rychlý přechod od rešerše k rozhodnutí: GO / CONDITIONAL GO / NO-GO.</div>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

phases = [("Upload", 0), ("AI summary", 1), ("Patent search", 2), ("Scorecard", 3), ("Analysis", 4), ("Export", 5)]
phase_html = '<div class="phase-bar">'
for label, idx in phases:
    cls = "phase-done" if idx < st.session_state.phase else ("phase-active" if idx == st.session_state.phase else "phase-pending")
    phase_html += f'<span class="phase-pill {cls}">{label}</span>'
st.markdown(phase_html + "</div>", unsafe_allow_html=True)

# Upload / manual input
st.markdown("### Vstupní technologie")
st.caption("Nahraj PDF dokument, nebo níže vlož technický popis ručně.")
uploaded = st.file_uploader("PDF dokument", type=["pdf"], label_visibility="collapsed")
if uploaded and not st.session_state.pdf_text:
    with st.spinner("Extrahuji text..."):
        text = extract_pdf_text(uploaded)
        if text:
            st.session_state.pdf_text = text
            st.session_state.pdf_name = uploaded.name
            st.session_state.phase = 1
            st.rerun()
        else:
            st.error("Z PDF se nepodařilo vytáhnout text. Možná jde o sken bez OCR.")

if not st.session_state.pdf_text:
    st.caption("PDF není nutné. Pro rychlý test můžeš technologii vložit ručně.")
    manual_text = st.text_area("Nebo vlož technický popis ručně", height=180, placeholder="Stručný popis technologie, materiálu, metody, aplikací, výhod a aktuálního stavu projektu...")
    if st.button("✍️ Použít vložený text", disabled=len(manual_text.strip()) < 80):
        st.session_state.pdf_text = manual_text.strip()
        st.session_state.pdf_name = "manual_input.txt"
        st.session_state.phase = 1
        st.rerun()

if st.session_state.pdf_text:
    with st.expander("📋 Extrahovaný / vložený text", expanded=False):
        st.text(st.session_state.pdf_text[:4000])

# Analyze doc
if st.session_state.phase >= 1 and not st.session_state.search_queries:
    st.markdown("---")
    st.markdown("### 🧠 AI pochopení technologie")
    if not gemini_key:
        st.warning("Zadej Gemini API klíč.")
    elif st.button("🚀 Analyzovat technologii", type="primary"):
        with st.spinner("Gemini analyzuje technologii..."):
            try:
                r = analyze_document(gemini_key, st.session_state.pdf_text, prompt_set=prompt_set)
                st.session_state.tech_summary = r["summary"]
                st.session_state.tech_keywords_en = r["keywords"]
                st.session_state.tech_domains = r.get("domains", "—")
                st.session_state.value_proposition = r.get("value_proposition", "—")
                st.session_state.substitutes = r.get("substitutes", "—")
                st.session_state.search_queries = r["queries"]
                st.session_state.phase = 2
                st.rerun()
            except Exception as e:
                st.error(str(e))

if st.session_state.search_queries:
    st.markdown("---")
    st.markdown("### 🔍 Vyhledávací dotazy")
    st.info(f"**Shrnutí:** {st.session_state.tech_summary}")
    st.caption(f"**Domény:** {st.session_state.tech_domains}")
    st.caption(f"**Value proposition:** {st.session_state.value_proposition}")
    st.caption(f"**Substituty:** {st.session_state.substitutes}")
    st.caption(f"**Klíčová slova:** {st.session_state.tech_keywords_en}")
    updated = []
    labels = ["🎯 Jádro technologie", "📱 Aplikace 1", "🏥 Aplikace 2", "⚡ Aplikace 3", "🧪 Materiál"]
    for i, q in enumerate(st.session_state.search_queries):
        updated.append(st.text_input(labels[i] if i < len(labels) else f"Dotaz {i + 1}", value=q, key=f"q_{i}"))
    st.session_state.search_queries = updated

# Search + filter
if st.session_state.phase >= 2 and st.session_state.search_queries and not st.session_state.patents_raw:
    st.markdown("---")
    if not serpapi_key:
        st.warning("Zadej SerpApi Key.")
    if st.button("🔎 Spustit patentovou rešerši + AI filtr", type="primary", disabled=not serpapi_key):
        all_patents, seen = [], set()
        progress = st.progress(0, text="Rešerše...")
        for qi, q in enumerate(st.session_state.search_queries):
            progress.progress(int((qi / len(st.session_state.search_queries)) * 35), text=f"Dotaz {qi + 1}: {q[:48]}...")
            try:
                results = search_google_patents(serpapi_key, q, max_patents_per_query)
                st.toast(f"Dotaz {qi + 1}: nalezeno {len(results)} patentů")
                for p in results:
                    if p["pub_number"] not in seen:
                        seen.add(p["pub_number"])
                        p["source_query"] = q
                        all_patents.append(p)
            except Exception as e:
                st.error(f"Dotaz {qi + 1} selhal: {e}")
            time.sleep(0.3)
        st.session_state.patents_raw = all_patents
        if not all_patents:
            st.error("Nebyly nalezeny žádné patenty. Zkontroluj SerpApi klíč a dotazy.")
            progress.empty()
            st.stop()
        progress.progress(48, text=f"{len(all_patents)} patentů. AI filtr...")
        if gemini_key:
            st.session_state.patents_filtered = filter_patents(gemini_key, all_patents, st.session_state.tech_summary, relevance_threshold, prompt_set=prompt_set)
        else:
            st.session_state.patents_filtered = all_patents
        progress.progress(75, text="OpenAlex...")
        try:
            st.session_state.openalex_results = search_openalex(st.session_state.tech_keywords_en, max_openalex)
        except Exception as e:
            st.warning(f"OpenAlex selhal: {e}")
        analysis_patents = st.session_state.patents_filtered or st.session_state.patents_raw[:20]
        stats = compute_stats(analysis_patents)
        st.session_state.scorecard = compute_decision_score(st.session_state.patents_filtered, st.session_state.patents_raw, st.session_state.openalex_results, stats)
        progress.progress(100, text="Hotovo!")
        time.sleep(0.3)
        progress.empty()
        st.session_state.phase = 4
        st.rerun()

# Results
if st.session_state.patents_raw:
    st.markdown("---")
    st.markdown("### 🧭 Decision dashboard")
    analysis_patents = st.session_state.patents_filtered or st.session_state.patents_raw[:20]
    stats = compute_stats(analysis_patents)
    if not st.session_state.scorecard:
        st.session_state.scorecard = compute_decision_score(st.session_state.patents_filtered, st.session_state.patents_raw, st.session_state.openalex_results, stats)
    render_score_dashboard(st.session_state.scorecard)

    with st.expander("Evidence, rizika a doporučené validace", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Evidence**")
            for item in st.session_state.scorecard.get("evidence", []):
                st.write("• " + item)
        with c2:
            st.markdown("**Rizika**")
            for item in st.session_state.scorecard.get("risk_flags", []):
                st.write("• " + item)
        with c3:
            st.markdown("**Další validace**")
            for item in st.session_state.scorecard.get("next_steps", []):
                st.write("• " + item)

    raw_c = len(st.session_state.patents_raw)
    filt_c = len(st.session_state.patents_filtered)
    commercial = [r for r in st.session_state.openalex_results if r.get("is_commercial")]
    st.markdown(
        f"""<div class="metric-grid">
        <div class="metric-card"><div class="num">{raw_c} → {filt_c}</div><div class="label">Patentů</div></div>
        <div class="metric-card"><div class="num">{len(stats['families'])}</div><div class="label">Rodin</div></div>
        <div class="metric-card"><div class="num">{len(stats['countries'])}</div><div class="label">Států/úřadů</div></div>
        <div class="metric-card"><div class="num">{len(stats['assignees'])}</div><div class="label">Firem</div></div>
        <div class="metric-card"><div class="num">{len(commercial)}</div><div class="label">Komerční</div></div>
    </div>""",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["✅ Relevantní patenty", "📋 Všechny patenty", "👪 Rodiny + státy", "📚 Publikace", "📈 Statistiky"])
    with tab1:
        if st.session_state.patents_filtered:
            for pat in st.session_state.patents_filtered:
                render_patent_card(pat)
        else:
            st.info("Žádné patenty neprošly nastaveným prahem relevance. Scorecard používá top raw výsledky jako slabší evidenci.")
    with tab2:
        for pat in st.session_state.patents_raw:
            render_patent_card(pat)
    with tab3:
        import pandas as pd
        st.markdown("#### Odhad patentových rodin")
        st.caption("Rodiny jsou orientační: pokud API nevrací family ID, aplikace seskupuje podle názvu a přihlašovatele.")
        if stats.get("families"):
            df_f = pd.DataFrame(stats["families"])[["title", "applicant", "patent_count", "country_count", "countries", "country_names", "publication_numbers", "best_relevance"]]
            df_f.columns = ["Název", "Majitel", "Záznamů", "Států/úřadů", "Kódy", "Státy/úřady", "Publikační čísla", "Nejvyšší relevance"]
            st.dataframe(df_f, use_container_width=True, hide_index=True)
        st.markdown("#### Geografické pokrytí")
        if stats.get("countries"):
            df_country = pd.DataFrame([(code, get_jurisdiction_name(code), count) for code, count in stats["countries"]], columns=["Kód", "Stát / úřad", "Počet"])
            st.dataframe(df_country, use_container_width=True, hide_index=True)
    with tab4:
        if st.session_state.openalex_results:
            for pub in st.session_state.openalex_results:
                badge = "🏢 " if pub.get("is_commercial") else ""
                st.markdown(f"""<div class="patent-card"><h4>{badge}{pub.get('title', '—')}</h4><div class="meta">Rok: {pub.get('year', '—')} · Citací: {pub.get('cited_by', 0)}× · Instituce: {', '.join(pub.get('institutions', [])[:3])}</div></div>""", unsafe_allow_html=True)
        else:
            st.info("OpenAlex nevrátil žádné výsledky.")
    with tab5:
        import pandas as pd
        st.markdown("#### Top přihlašovatelé patentů")
        if stats["assignees"]:
            st.dataframe(pd.DataFrame(stats["assignees"], columns=["Firma/Instituce", "Počet patentů"]), use_container_width=True, hide_index=True)
        st.markdown("#### Patentová aktivita po letech")
        if stats["yearly"]:
            df_y = pd.DataFrame(stats["yearly"], columns=["Rok", "Počet"])
            df_y = df_y[df_y["Počet"] > 0]
            if not df_y.empty:
                st.bar_chart(df_y.set_index("Rok"), use_container_width=True)
        st.markdown("#### Geografické rozložení")
        if stats["countries"]:
            df_c = pd.DataFrame([(code, get_jurisdiction_name(code), count) for code, count in stats["countries"]], columns=["Kód", "Stát / patentový úřad", "Počet"])
            st.dataframe(df_c, use_container_width=True, hide_index=True)

# Final analysis
if st.session_state.phase >= 4 and st.session_state.patents_raw and not st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 🤖 Kritická AI analýza")
    if not gemini_key:
        st.warning("Zadej Gemini API klíč.")
    elif st.button("🧪 Spustit finální analýzu", type="primary"):
        with st.spinner("Gemini připravuje finální analýzu..."):
            try:
                analysis_patents = st.session_state.patents_filtered or st.session_state.patents_raw[:20]
                if not st.session_state.patents_filtered:
                    st.warning("Žádný patent neprošel filtrem relevance. Pro analýzu použiju top raw výsledky jako slabší evidenci.")
                stats = compute_stats(analysis_patents)
                scorecard = st.session_state.scorecard or compute_decision_score(st.session_state.patents_filtered, st.session_state.patents_raw, st.session_state.openalex_results, stats)
                analysis = run_analysis(gemini_key, st.session_state.tech_summary, analysis_patents, st.session_state.openalex_results, st.session_state.pdf_text, stats, scorecard, prompt_set=prompt_set)
                st.session_state.analysis = analysis
                st.session_state.phase = 5
                save_to_history({
                    "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M"),
                    "pdf_name": st.session_state.pdf_name,
                    "prompt_set": prompt_set,
                    "tech_summary": st.session_state.tech_summary,
                    "tech_domains": st.session_state.tech_domains,
                    "value_proposition": st.session_state.value_proposition,
                    "search_queries": st.session_state.search_queries,
                    "scorecard": scorecard,
                    "patents_raw_count": len(st.session_state.patents_raw),
                    "patents_filtered": [{"title": p.get("title", "—"), "applicant": p.get("applicant", "—"), "pub_number": p.get("pub_number", "—"), "country": p.get("country", "—"), "relevance": p.get("relevance", 0), "rel_type": p.get("rel_type", "—")} for p in st.session_state.patents_filtered],
                    "analysis": analysis,
                })
                st.rerun()
            except Exception as e:
                st.error(str(e))

if st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 🤖 Výsledek analýzy")
    st.markdown(f'<div class="analysis-box">{st.session_state.analysis}</div>', unsafe_allow_html=True)

# Export
if st.session_state.phase >= 5 and st.session_state.analysis:
    st.markdown("---")
    st.markdown("### 📥 Export")
    col1, col2, col3 = st.columns(3)
    export_patents = st.session_state.patents_filtered or st.session_state.patents_raw
    export_stats = compute_stats(export_patents)
    export_scorecard = st.session_state.scorecard or compute_decision_score(st.session_state.patents_filtered, st.session_state.patents_raw, st.session_state.openalex_results, export_stats)
    with col1:
        if st.button("📄 Word report", type="primary"):
            with st.spinner("Generuji .docx..."):
                try:
                    buf = generate_docx(st.session_state.tech_summary, st.session_state.search_queries, len(st.session_state.patents_raw), export_patents, st.session_state.openalex_results, st.session_state.analysis, st.session_state.pdf_name, relevance_threshold, export_stats, export_scorecard, prompt_set=prompt_set)
                    st.session_state.doc_content = buf.getvalue()
                    st.success("Hotovo!")
                except Exception as e:
                    st.error(str(e))
    with col2:
        if st.button("📊 Excel tabulka", type="primary"):
            with st.spinner("Generuji .xlsx..."):
                try:
                    buf = generate_xlsx(export_patents, st.session_state.openalex_results, st.session_state.tech_summary, export_scorecard)
                    st.session_state.xlsx_content = buf.getvalue()
                    st.success("Hotovo!")
                except Exception as e:
                    st.error(str(e))
    with col3:
        st.markdown(f"**Prompt sada:** `{prompt_set}`")
        st.markdown(f"**Verdikt:** `{export_scorecard.get('verdict', '—')}`")
        st.markdown(f"**Skóre:** `{export_scorecard.get('score_100', '—')}/100`")

    dl1, dl2, dl3 = st.columns(3)
    if st.session_state.doc_content:
        with dl1:
            st.download_button("⬇️ Stáhnout .docx", data=st.session_state.doc_content, file_name=f"reserse_{datetime.now().strftime('%Y%m%d_%H%M')}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if st.session_state.xlsx_content:
        with dl2:
            st.download_button("⬇️ Stáhnout .xlsx", data=st.session_state.xlsx_content, file_name=f"patenty_scorecard_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if st.session_state.phase > 0:
    st.markdown("---")
    if st.button("🔄 Nová analýza (reset)"):
        for k in defaults:
            st.session_state[k] = defaults[k]
        st.session_state.active_prompt_set = prompt_set
        st.rerun()

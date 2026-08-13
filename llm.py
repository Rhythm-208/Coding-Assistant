"""
Centralised LLM factory with rate‑limiting and automatic retries.

Every node should import its LLM / agent from here instead of creating
its own model instance. This avoids duplicate token costs and keeps configuration in one place.
"""

# Load environment variables as early as possible (before any LangChain imports)
from pathlib import Path
from dotenv import load_dotenv
import os

# Resolve .env located at the repository root (two levels up from this file)
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")

# Propagate LangSmith API key for LangChain compatibility
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGCHAIN_API_KEY", os.getenv("LANGSMITH_API_KEY"))
else:
    raise RuntimeError("LANGSMITH_API_KEY not found in .env – LangSmith tracing cannot work.")
# Ensure tracing is enabled before any LangChain objects are instantiated
os.environ.setdefault("LANGSMITH_TRACING", "true")
# Default to local Ollama endpoint if not set
if not os.getenv("LOCAL_LLM_ENDPOINT"):
    os.environ["LOCAL_LLM_ENDPOINT"] = "http://localhost:11434/v1"

# Standard imports after env handling
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import create_react_agent

# Conditional imports for different LLM providers (installed lazily)
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

from tools import read_file_numbered, list_folder_content, read_file_exact

# Stay safely under the 30 RPM free‑tier limit for Gemini (≈24 req/min)
_rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.4,   # 0.4 req/s → 24 req/min
    check_every_n_seconds=0.5,
    max_bucket_size=5,          # allow small bursts
)


# ── shared tools list ────────────────────────────────────────────────
_tools = [read_file_numbered, list_folder_content, read_file_exact]


# ── LLM instances ────────────────────────────────────────────────────
def get_llm(model=None, **kwargs):
    """Return a rate‑limited LLM instance based on environment configuration.
    Supports:
    • Gemini via `ChatGoogleGenerativeAI`
    • OpenAI/OSS via `ChatOpenAI`
    • Any local LLM exposing an OpenAI‑compatible API (set LOCAL_LLM_ENDPOINT).
    """
    # Determine model name, fallback to Ollama default if using local endpoint
    model_name = model or os.getenv("LLM_MODEL")
    if not model_name and os.getenv("LOCAL_LLM_ENDPOINT"):
        model_name = "qwen2.5-coder:7b"
    if not model_name:
        model_name = "gemini-2.0-flash-lite"
    defaults = dict(
        model=model_name,
        max_retries=5,
        rate_limiter=_rate_limiter,
    )
    defaults.update(kwargs)

    # 1️⃣ Gemini models (prefix "gemini")
    if model_name.lower().startswith("gemini"):
        if ChatGoogleGenerativeAI is None:
            raise ImportError("ChatGoogleGenerativeAI not installed.")
        return ChatGoogleGenerativeAI(**defaults)

    # 2️⃣ OpenAI / OSS models (prefix "gpt" or "openai")
    if model_name.lower().startswith(("gpt", "openai")):
        if ChatOpenAI is None:
            raise ImportError("ChatOpenAI not installed.")
        return ChatOpenAI(**defaults)

    # 3️⃣ Fallback: assume a local LLM exposing an OpenAI‑compatible endpoint
    #    Users can set LOCAL_LLM_ENDPOINT and optionally LOCAL_LLM_API_KEY.
    local_endpoint = os.getenv("LOCAL_LLM_ENDPOINT")
    if local_endpoint:
        if ChatOpenAI is None:
            raise ImportError("ChatOpenAI required for local LLM endpoint.")
        # Override the base URL and, if provided, the API key.
        defaults["base_url"] = local_endpoint.rstrip("/")
        local_key = os.getenv("LOCAL_LLM_API_KEY")
        if local_key:
            defaults["api_key"] = local_key
        else:
            defaults["api_key"] = "dummy-key-for-local"
        return ChatOpenAI(**defaults)

    # If none matched, raise a clear error.
    raise ValueError(f"Unsupported LLM_MODEL '{model_name}'. Set LLM_MODEL to a Gemini, OpenAI, or configure LOCAL_LLM_ENDPOINT.")


# Single shared LLM — all agents below use the same instance so we
# don't create multiple ChatGoogleGenerativeAI objects unnecessarily.
llm = get_llm()

# Dedicated Gemini LLM for Propose_rewrite
propose_rewrite_llm = get_llm(model="gemini-2.5-flash")

# ── Pre-built ReAct agents ───────────────────────────────────────────

# Used by Diagnose node
diagnose_agent = create_react_agent(llm, tools=_tools)

# Used by Analyze node
analyze_agent = create_react_agent(llm, tools=_tools)

# Used by Propose_rewrite node (propose_patch)
propose_rewrite_agent = create_react_agent(propose_rewrite_llm, tools=_tools)

# Used by Propose_code_changes node
propose_code_changes_agent = create_react_agent(llm, tools=_tools)

"""
Centralised LLM factory with rate-limiting and automatic retries.

Every node should import its LLM / agent from here instead of creating
its own ChatGoogleGenerativeAI or create_react_agent instance.
This avoids duplicate token costs and keeps configuration in one place.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv
from pathlib import Path

from tools import read_file_numbered, list_folder_content

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# Stay safely under the 30 RPM free-tier limit for gemini-2.0-flash-lite
_rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.4,   # ~24 req/min
    check_every_n_seconds=0.5,
    max_bucket_size=5,         # allow small bursts
)


# ── shared tools list ────────────────────────────────────────────────
_tools = [read_file_numbered, list_folder_content]


# ── LLM instances ────────────────────────────────────────────────────
def get_llm(**kwargs):
    """Return a rate-limited, retry-enabled Gemini LLM instance."""
    defaults = dict(
        model="gemini-2.0-flash-lite",
        max_retries=5,
        rate_limiter=_rate_limiter,
    )
    defaults.update(kwargs)
    return ChatGoogleGenerativeAI(**defaults)


# Single shared LLM — all agents below use the same instance so we
# don't create multiple ChatGoogleGenerativeAI objects unnecessarily.
llm = get_llm()


# ── Pre-built ReAct agents ───────────────────────────────────────────

# Used by Diagnose node
diagnose_agent = create_react_agent(llm, tools=_tools)

# Used by Analyze node
analyze_agent = create_react_agent(llm, tools=_tools)

# Used by Propose_rewrite node (propose_patch)
propose_rewrite_agent = create_react_agent(llm, tools=_tools)

# Used by Propose_code_changes node
propose_code_changes_agent = create_react_agent(llm, tools=_tools)

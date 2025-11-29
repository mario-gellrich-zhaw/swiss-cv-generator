from src.data.models import SwissPersona
from src.generation.sampling import SamplingEngine
from src.generation.openai_client import call_openai_chat
from src.generation.prompts import build_summary_prompt, build_skills_prompt

engine = SamplingEngine()

def build_persona(preferred_canton: str = None, preferred_industry: str = None) -> SwissPersona:
    p = engine.sample_persona(preferred_canton, preferred_industry)
    # Try to generate summary & skills via OpenAI; fall back to simple templates if API not available
    summary_prompt = build_summary_prompt(p)
    summary = call_openai_chat(summary_prompt['system'], summary_prompt['user'])
    if not summary:
        summary = f"{p.full_name} ist ein/e {p.current_title} mit {int(p.experience_years)} Jahren Erfahrung in {p.industry}."
    skills_prompt = build_skills_prompt(p)
    skills_text = call_openai_chat(skills_prompt['system'], skills_prompt['user'])
    if skills_text:
        p.skills = [s.strip('- ').strip() for s in skills_text.splitlines() if s.strip()]
        if not p.skills:
            p.skills = ['Problem solving','Teamwork']
    else:
        # local fallback skills
        p.skills = ['Problem solving', 'Teamwork', 'Technical knowledge']
    p.summary = summary
    return p



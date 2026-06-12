"""AI-powered market intelligence for the dashboard.

Uses Google Gemini for:
1. Cross-asset narrative (dominant variable section)
2. TL;DR summaries of daily/weekly market reports

Falls back to heuristic when Gemini is unavailable.
"""

import logging
from src.calculations import DominantVariable, InstrumentData, TYPICAL_DAILY_VOL
from src.scraper import MarketReport
from src.cache import read_cache, write_cache

logger = logging.getLogger(__name__)


def _get_gemini_key() -> str | None:
    """Try to get Gemini API key from Streamlit secrets."""
    try:
        import streamlit as st
        gemini_section = st.secrets.get("gemini", {})
        return gemini_section.get("api_key") or gemini_section.get("key") or None
    except Exception:
        return None


def _call_gemini(prompt: str) -> str | None:
    """Call Gemini 2.0 Flash with a prompt. Returns None on failure."""
    api_key = _get_gemini_key()
    if not api_key:
        return None

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Cross-Asset Narrative (Dominant Variable Section)
# ---------------------------------------------------------------------------


def _build_moves_text(instruments: list[InstrumentData]) -> str:
    """Format instrument moves for prompt context."""
    lines = []
    for inst in instruments:
        daily = f"{inst.daily_change_pct:+.2f}%" if inst.daily_change_pct is not None else "N/A"
        weekly = f"{inst.weekly_change_pct:+.2f}%" if inst.weekly_change_pct is not None else "N/A"
        lines.append(f"{inst.ticker} ({inst.macro_significance}): Daily {daily}, Weekly {weekly}")
    return "\n".join(lines)


def generate_cross_asset_narrative(
    instruments: list[InstrumentData],
    dominant: DominantVariable,
    daily_report: MarketReport | None = None,
) -> str:
    """Generate a cross-asset narrative explaining what drove markets.

    Uses Gemini to produce 2-3 sentences explaining the causal chain
    across instruments. Falls back to heuristic.

    Args:
        instruments: All instrument data.
        dominant: Identified dominant variable.
        daily_report: Scraped daily report for context.

    Returns:
        A 2-3 sentence cross-asset narrative.
    """
    # Check cache first (one narrative per day)
    cache_key = "ai_narrative"
    cached = read_cache(cache_key, max_age_hours=6.0)
    if cached is not None:
        return cached.get("narrative", "")

    moves_text = _build_moves_text(instruments)
    report_context = ""
    if daily_report and daily_report.available:
        report_context = daily_report.body[:1000]

    prompt = f"""You are a macro strategist. Based on today's market data and report, write a 2-3 sentence cross-asset narrative explaining:
1. What was the PRIMARY driver (the causal factor, not just biggest mover)
2. How it transmitted across asset classes (the chain reaction)
3. What this tells us about the market regime right now

Be specific and causal. Think like a hedge fund CIO morning note. No bullet points, just flowing prose. Max 60 words.

Today's moves:
{moves_text}

Dominant variable (vol-adjusted): {dominant.ticker} ({dominant.macro_significance}) at {dominant.daily_change_pct:+.2f}%

Daily report context:
{report_context}

Cross-asset narrative:"""

    result = _call_gemini(prompt)

    if result:
        # Clean up
        result = result.strip('"').strip("'").strip()
        write_cache(cache_key, {"narrative": result})
        return result

    # Heuristic fallback
    narrative = _heuristic_narrative(instruments, dominant)
    return narrative


def _heuristic_narrative(
    instruments: list[InstrumentData],
    dominant: DominantVariable,
) -> str:
    """Generate a heuristic cross-asset narrative."""
    ticker = dominant.ticker
    pct = dominant.daily_change_pct
    direction = "higher" if pct > 0 else "lower"

    spy = next((i.daily_change_pct for i in instruments if i.ticker == "SPY" and i.daily_change_pct is not None), None)
    vix = next((i.daily_change_pct for i in instruments if i.ticker == "VIX" and i.daily_change_pct is not None), None)
    tnx = next((i.daily_change_pct for i in instruments if i.ticker == "US10Y" and i.daily_change_pct is not None), None)
    dxy = next((i.daily_change_pct for i in instruments if i.ticker == "DXY" and i.daily_change_pct is not None), None)
    oil = next((i.daily_change_pct for i in instruments if i.ticker == "Oil" and i.daily_change_pct is not None), None)

    # Build narrative based on cross-asset patterns
    if ticker == "VIX" and pct > 3 and spy and spy < -0.5:
        narrative = (
            f"Risk-off regime: VIX spiking {pct:+.1f}% as equities sell off "
            f"(SPY {spy:+.1f}%). "
        )
        if tnx and tnx > 0:
            narrative += "Yields rising into the selloff suggests rate fears, not a flight-to-quality bid."
        elif tnx and tnx < 0:
            narrative += "Yields falling confirms flight-to-quality — this is a growth scare, not a rate shock."
        return narrative

    elif ticker == "US10Y" and abs(pct) > 0.3:
        narrative = f"Rates driving: 10Y yield moved {pct:+.2f}% — "
        if pct > 0 and spy and spy < 0:
            narrative += "higher yields pressuring equity valuations via discount rates. "
            if dxy and dxy > 0:
                narrative += "Dollar bid confirms tighter financial conditions narrative."
            return narrative
        elif pct < 0 and spy and spy > 0:
            narrative += "falling yields supporting risk appetite. "
            narrative += "Market pricing in easier policy ahead, duration rally pulling equities higher."
            return narrative
        else:
            narrative += f"{'hawkish' if pct > 0 else 'dovish'} rates repricing rippling through cross-asset."
            return narrative

    elif ticker == "DXY":
        if pct > 0.2:
            narrative = "Dollar strength tightening global liquidity. "
            if spy and spy < 0:
                narrative += "Equities lower as stronger USD compresses multinational earnings and EM flows."
            return narrative
        else:
            narrative = "Dollar weakness easing financial conditions globally. "
            if spy and spy > 0:
                narrative += "Risk assets bid as weaker USD supports global liquidity and commodity pricing."
            return narrative

    elif ticker == "Oil" and abs(pct) > 1.5:
        if pct > 0:
            narrative = f"Energy shock: oil +{pct:.1f}% driving inflation expectations higher. "
            if tnx and tnx > 0:
                narrative += "Yields moving in sympathy — market pricing stagflationary impulse."
            return narrative
        else:
            narrative = f"Oil weakness ({pct:+.1f}%) signaling demand concerns. "
            if spy and spy < 0:
                narrative += "Equities confirming growth worry narrative."
            return narrative

    elif ticker in ("SPY", "QQQ"):
        if pct < -1:
            narrative = f"Equity-led selloff: {ticker} {pct:+.1f}%. "
            if vix and vix > 3:
                narrative += f"VIX confirmation ({vix:+.1f}%) suggests systematic deleveraging, not just profit-taking."
            else:
                narrative += "Orderly selling without panic — likely positioning adjustment."
            return narrative
        else:
            narrative = f"Risk-on: {ticker} {direction} {abs(pct):.1f}%. "
            if tnx and tnx < 0:
                narrative += "Lower yields providing tailwind for growth/duration assets."
            return narrative

    # Generic fallback
    return (
        f"{dominant.macro_significance} ({ticker}) moved {pct:+.2f}% — "
        f"the largest vol-adjusted move across the dashboard today, "
        f"suggesting it's the primary variable to track for follow-through."
    )


# ---------------------------------------------------------------------------
# TL;DR Report Summaries
# ---------------------------------------------------------------------------


def generate_report_tldr(report: MarketReport, report_type: str = "daily") -> str | None:
    """Generate a TL;DR summary of a market report.

    Args:
        report: The scraped MarketReport.
        report_type: "daily" or "weekly".

    Returns:
        A 3-4 bullet TL;DR summary, or None if unavailable.
    """
    if not report.available or not report.body.strip():
        return None

    # Check cache
    cache_key = f"tldr_{report_type}"
    cached = read_cache(cache_key, max_age_hours=4.0 if report_type == "daily" else 12.0)
    if cached is not None:
        return cached.get("tldr", None)

    prompt = f"""Summarize this {report_type} market report into exactly 3-4 bullet points. Each bullet should be one concise sentence capturing a key takeaway. Focus on: what moved, why it moved, and what it means going forward. No headers, just bullets starting with •.

Report:
{report.body[:3000]}

TL;DR:"""

    result = _call_gemini(prompt)

    if result:
        result = result.strip()
        write_cache(cache_key, {"tldr": result})
        return result

    # No heuristic fallback for TL;DR — requires AI
    return None


# ---------------------------------------------------------------------------
# Combined AI call (sequential with caching)
# ---------------------------------------------------------------------------


def generate_all_ai_content(
    instruments: list[InstrumentData],
    dominant: DominantVariable,
    daily_report: MarketReport | None,
    weekly_report: MarketReport | None,
    weekly_dominant: DominantVariable | None = None,
) -> dict[str, str | None]:
    """Generate all AI content, using cache and making Gemini calls as needed.

    Makes up to 4 separate Gemini calls (narrative, weekly narrative, daily TL;DR, weekly TL;DR),
    each cached independently. Skips calls for already-cached content.

    Returns a dict with keys: 'narrative', 'weekly_narrative', 'tldr_daily', 'tldr_weekly'.
    """
    import time

    result: dict[str, str | None] = {
        "narrative": None,
        "weekly_narrative": None,
        "tldr_daily": None,
        "tldr_weekly": None,
    }

    # --- Daily Narrative ---
    cached_narrative = read_cache("ai_narrative", max_age_hours=6.0)
    if cached_narrative:
        result["narrative"] = cached_narrative.get("narrative")
    else:
        narrative = _generate_narrative_via_gemini(instruments, dominant, daily_report)
        if narrative:
            result["narrative"] = narrative
            write_cache("ai_narrative", {"narrative": narrative})
        else:
            result["narrative"] = _heuristic_narrative(instruments, dominant)

    # --- Weekly Narrative ---
    cached_weekly_narrative = read_cache("ai_weekly_narrative", max_age_hours=12.0)
    if cached_weekly_narrative:
        result["weekly_narrative"] = cached_weekly_narrative.get("narrative")
    elif weekly_dominant:
        time.sleep(1)
        weekly_narr = _generate_weekly_narrative_via_gemini(
            instruments, weekly_dominant, weekly_report
        )
        if weekly_narr:
            result["weekly_narrative"] = weekly_narr
            write_cache("ai_weekly_narrative", {"narrative": weekly_narr})
        else:
            result["weekly_narrative"] = _heuristic_narrative(instruments, weekly_dominant)

    # --- Daily TL;DR ---
    cached_daily = read_cache("tldr_daily", max_age_hours=4.0)
    if cached_daily:
        result["tldr_daily"] = cached_daily.get("tldr")
    elif daily_report and daily_report.available and daily_report.body.strip():
        time.sleep(1)
        tldr = _generate_tldr_via_gemini(daily_report, "daily")
        if tldr:
            result["tldr_daily"] = tldr
            write_cache("tldr_daily", {"tldr": tldr})

    # --- Weekly TL;DR ---
    cached_weekly = read_cache("tldr_weekly", max_age_hours=12.0)
    if cached_weekly:
        result["tldr_weekly"] = cached_weekly.get("tldr")
    elif weekly_report and weekly_report.available and weekly_report.body.strip():
        time.sleep(1)
        tldr = _generate_tldr_via_gemini(weekly_report, "weekly")
        if tldr:
            result["tldr_weekly"] = tldr
            write_cache("tldr_weekly", {"tldr": tldr})

    return result


def _generate_narrative_via_gemini(
    instruments: list[InstrumentData],
    dominant: DominantVariable,
    daily_report: MarketReport | None,
) -> str | None:
    """Generate cross-asset narrative via Gemini."""
    moves_text = _build_moves_text(instruments)
    report_context = ""
    if daily_report and daily_report.available:
        report_context = daily_report.body[:800]

    prompt = f"""You are a macro strategist. Write a 2-3 sentence cross-asset narrative explaining:
1. What was the PRIMARY driver today
2. How it transmitted across asset classes
3. What this tells us about the current market regime

Be specific and causal. Max 60 words. No preamble, just the narrative.

Today's moves:
{moves_text}

Dominant variable: {dominant.ticker} ({dominant.macro_significance}) at {dominant.daily_change_pct:+.2f}%

Report context: {report_context[:500]}"""

    return _call_gemini(prompt)


def _generate_weekly_narrative_via_gemini(
    instruments: list[InstrumentData],
    dominant: DominantVariable,
    weekly_report: MarketReport | None,
) -> str | None:
    """Generate weekly cross-asset narrative via Gemini."""
    # Build weekly moves
    lines = []
    for inst in instruments:
        if inst.weekly_change_pct is not None:
            lines.append(f"{inst.ticker} ({inst.macro_significance}): {inst.weekly_change_pct:+.2f}% week")
    moves_text = "\n".join(lines)

    report_context = ""
    if weekly_report and weekly_report.available:
        report_context = weekly_report.body[:1200]

    prompt = f"""You are a macro strategist writing a weekly market wrap. Write a short paragraph (3-4 sentences, max 80 words) explaining:
1. What was the dominant THEME of the week (not just biggest mover)
2. The cross-asset narrative — how did rates, equities, FX, and commodities tell a coherent story?
3. What regime or shift does this week signal going forward?

Use the weekly report context for fundamental reasoning. Be specific about causality. No preamble, just the paragraph.

This week's moves:
{moves_text}

Week's dominant variable: {dominant.ticker} ({dominant.macro_significance}) at {dominant.daily_change_pct:+.2f}%

Weekly report context:
{report_context}"""

    return _call_gemini(prompt)


def _generate_tldr_via_gemini(report: MarketReport, report_type: str) -> str | None:
    """Generate TL;DR bullets via Gemini."""
    prompt = f"""Summarize this {report_type} market report into exactly 3-4 bullet points.
Each bullet: one concise sentence with a key takeaway.
Focus on: what moved, why, and what it means going forward.
Format: start each bullet with •

Report:
{report.body[:3000]}"""

    return _call_gemini(prompt)

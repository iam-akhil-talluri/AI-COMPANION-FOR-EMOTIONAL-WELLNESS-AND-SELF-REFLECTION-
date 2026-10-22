"""Safety and moderation layer.

Runs BEFORE the AI sees a message and does not rely on the AI's judgement. The rules are
fast, free, testable and cannot be talked out of their decisions. The OpenAI Moderation
API adds an optional second opinion; the higher risk of the two wins.

Risk levels (lowest to highest) and what the companion does:
    low       everyday stress, reflection, motivation          -> AI reply
    moderate  diagnosis / medication / therapy requests,       -> AI reply with a boundary note
              identity questions, dependency, injection
    elevated  severe distress, isolation, worry about someone, -> AI reply with a support note and
              a negated self-harm mention, abuse disclosure       support resources (abuse: reviewed
                                                                  template only, no AI)
    high      suicidal intent, self-harm, method requests,     -> reviewed crisis template and crisis
              immediate danger, harm to others                    resources; the AI is never called

Fail-closed rule: if the check cannot complete, SafetyServiceError is raised and the
caller must not call the AI.

The output check (check_output) validates every AI reply before the user sees it.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from app.content import POLICY_CANARY

logger = logging.getLogger(__name__)

RISK_ORDER = {"low": 0, "moderate": 1, "elevated": 2, "high": 3}
RISK_LEVELS = tuple(RISK_ORDER)


class SafetyServiceError(RuntimeError):
    """The safety check could not complete. Callers must fail closed."""


@dataclass(frozen=True)
class SafetyResult:
    risk_level: str = "low"
    # Most important first; the first one picks the response template and AI note.
    categories: tuple[str, ...] = field(default_factory=tuple)
    source: str = "rules"

    @property
    def primary_category(self) -> str | None:
        return self.categories[0] if self.categories else None

    @property
    def escalated(self) -> bool:
        """True for elevated and high risk: the user is shown support resources."""
        return RISK_ORDER[self.risk_level] >= RISK_ORDER["elevated"]


# ---------------------------------------------------------------------------
# Input rules. Patterns run on normalized text (lowercase, straight apostrophes,
# punctuation removed). Inside a level, the first matching category is primary.
# ---------------------------------------------------------------------------

_CONDITIONS = (
    r"(depression|anxiety|an anxiety disorder|adhd|add|bipolar|ptsd|ocd|bpd|borderline|autism|schizophrenia|"
    r"insomnia|an eating disorder|a personality disorder|a mood disorder|a panic disorder|a mental illness)"
)
_SELF_HARM_VERBS = (r"(hurt|hurting|harm|harming|cut|cutting|burn|burning|punish|punishing|injure|injuring|"
                    r"starve|starving)")
_OTHERS = r"(he|she|they|my \w+|a friend|someone|somebody|someone i know)"

RULES: dict[str, list[tuple[str, list[str]]]] = {
    "high": [
        ("harmful_instructions", [
            r"\bhow (much|many) \w+( \w+)? (to|would|will|does it take to|until i) (overdose|kill|die|od)\b",
            r"\b(lethal|fatal|deadly|toxic) (dose|amount|dosage)\b",
            r"\boverdos(e|ing)\b",
            r"\b(painless|easiest|quickest|fastest|best|surest) (way|ways|method|methods) to "
            r"(die|kill myself|end it)\b",
            r"\b(ways|methods) to (die|kill myself|end (it|my life)|commit suicide)\b",
            r"\bhow (do i|to|can i|should i|would i) (hang|kill|hurt|poison|cut|harm|drown|shoot) (myself|someone)\b",
            r"\b(tell|show|teach) me how to (hurt|kill|harm|cut|poison) (myself|someone)\b",
        ]),
        ("suicidal_intent", [
            r"\b(kill|killing) myself\b",
            r"\bend(ing)? (my|it) (own )?life\b",
            r"\bend it all\b",
            r"\btake my (own )?life\b",
            r"\b(want|wanna|going|plan(ning)?|ready|deserve) to die\b",
            r"\bwish i (was|were|could be) dead\b",
            r"\bsuicid(e|al)\b",
            r"\bbetter off (dead|without me)\b",
            r"\bno (reason|point) (in |to )?(live|living|keep going|going on|being alive)\b",
            r"\bwhat'?s the point (of|in) (living|life|going on|being alive)\b",
            r"\bdon'?t want to (live|be alive|exist|wake up|be here anymore)\b",
            r"\b(sleep|go to sleep|fall asleep) and (never|not) wake up\b",
            r"\bnever wake up again\b",
            r"\b(i'?m|i am|so) done with (life|living)\b",
            r"\b(nobody|no one) would (care|notice|miss me) if i (was|were) (gone|dead)\b",
            r"\bkms\b",
            r"\bunaliv(e|ing)( myself)?\b",
            r"\b(want|wanna) to disappear (forever|for good)\b",
        ]),
        ("self_harm", [
            rf"\b(want|wanna|going|gonna|urge|urges|feel like|thinking about|thought about|been|keep|kept|started|"
            rf"start|stop myself from) (to )?{_SELF_HARM_VERBS} myself\b",
            r"\b(cut|cutting|burn|burning|harm|harming) myself\b",
            r"\bself[- ]?harm(ing)?\b",
            r"\bi (cut|burned|burnt) (my|myself)\b",
        ]),
        ("immediate_danger", [
            r"\b(i'?m|i am) (in danger|not safe)\b",
            r"\bnot safe (right now|at home|here)\b",
            r"\b(he|she|they|someone|somebody) (is|are|'s|'re) (going to|gonna|trying to|about to) "
            r"(hurt|kill|attack) me\b",
            r"\b(has|have|is holding|is pointing|pulled) a (gun|knife|weapon)\b",
            r"\bthreaten(ed|ing|s)? to kill (me|us)\b",
            r"\b(i'?m|i am) being (attacked|followed|hurt|beaten|held)\b",
        ]),
        ("harm_to_others", [
            r"\b(want|wanna|going|gonna|plan(ning)?|about|ready) to (kill|hurt|attack|stab|shoot|poison|strangle) "
            r"(him|her|them|someone|somebody|people|everyone|my \w+)\b",
        ]),
    ],
    "elevated": [
        ("abuse_disclosure", [
            r"\b(he|she|they|my \w+) (hits|hit|beats|beat|abuses|abused|chokes|choked|slaps|slapped|kicks|kicked|"
            r"punches|punched|pushes|pushed|touches|touched) me\b",
            r"\b(he|she|they|my \w+) (is |are |keeps )?(hurting|abusing) me\b",
            r"\b(abused|abusive|abusing me|abuse at home)\b",
            r"\b(sexually )?(assaulted|molested|raped)\b",
            r"\bdomestic (violence|abuse)\b",
        ]),
        ("severe_distress", [
            r"\bcan'?t (cope|take (it|this|much more)|go on|handle (it|this|anything) anymore|do this anymore)\b",
            r"\b(i'?m|i am) (not|no longer) able to cope\b",
            r"\b(i'?m|i am) falling apart\b",
            r"\bhopeless(ness)?\b",
            r"\bnothing (will ever|is ever going to|will) get better\b",
            r"\bno way out\b",
            r"\bcan'?t stop crying\b",
            r"\b(i'?m|i am|i feel like|feel like) (such )?a burden\b",
            r"\bi hate my life\b",
            r"\b(want|wanna) to disappear\b",
            r"\beverything (is|feels) (pointless|meaningless)\b",
        ]),
        ("isolation", [
            r"\b(no ?one|nobody) (cares|would care|loves me|understands me|wants me|likes me)\b",
            r"\bi have (no ?one|nobody)\b",
            r"\b(completely|totally|all) alone\b",
            r"\bno ?one to talk to\b",
        ]),
    ],
    "moderate": [
        ("prompt_injection", [
            r"\b(ignore|disregard|forget|override) (all |any |your |the |of |my )*(previous |prior |above |earlier |"
            r"system |safety |original )?(instructions|rules|prompts?|guidelines|programming)\b",
            r"\b(system|hidden|initial|original) (prompt|instructions|message)\b",
            r"\b(reveal|show|print|repeat|tell me|give me|what are) (me )?(your|the) (instructions|rules|prompt|"
            r"system message|safety rules)\b",
            r"\b(developer|god|dan|unrestricted|jailbreak) mode\b",
            r"\bjailbreak\b",
            r"\b(pretend|act like|roleplay|role-play|role play) (you are|you're|to be|as|that you are)\b",
            r"\b(disable|turn off|bypass|remove|deactivate|ignore) (the |your |all )?(safety|filters?|moderation|"
            r"guardrails|restrictions)\b",
            r"\byou are (now )?(allowed|free) to\b",
            r"\bno (rules|restrictions|limits) (now|anymore)\b",
        ]),
        ("therapy_request", [
            r"\b(be|act as|become|you'?re|you are|are you) (my |a |an )?(therapist|psychologist|psychiatrist|"
            r"counsell?or|doctor)\b",
            r"\b(give me|do|provide|start) (therapy|a treatment plan|treatment|cbt)\b",
            r"\btreatment plan\b",
        ]),
        ("diagnosis_request", [
            rf"\b(do|could|might|can) i have {_CONDITIONS}\b",
            rf"\bi think i have {_CONDITIONS}\b",
            r"\b(am i|i think i'?m|i might be|i must be) (clinically )?"
            r"(depressed|bipolar|autistic|mentally ill|crazy)\b",
            r"\b(diagnose me|my diagnosis|a diagnosis|(can|could|will|would) you diagnose)\b",
        ]),
        ("medication_question", [
            r"\b(medications?|medicine|meds|antidepressants?|ssris?|prozac|zoloft|xanax|lexapro|adderall|"
            r"wellbutrin|sertraline|fluoxetine|benzos?|sleeping pills|melatonin|dosage|dose|prescription|prescribe)\b",
        ]),
        ("dependency", [
            r"\byou'?re (the only (one|person|thing)|my only (friend|one)|all i (need|have)|my best friend)\b",
            r"\byou are (the only (one|person|thing)|my only (friend|one)|all i (need|have)|my best friend)\b",
            r"\b(the )?only (one|person) i (need|trust|can talk to|have)\b",
            r"\bdon'?t (tell me to|make me) talk to (anyone|anybody|someone|people|humans|a therapist)\b",
            r"\bi love you\b",
            r"\bpromise (me )?(you'?ll|you will|you won'?t|to) (never |not |always )?(leave|stay|be there)\b",
            r"\bdon'?t (ever )?leave me\b",
            r"\bi don'?t need (humans|people|anyone|anybody|friends)\b",
            r"\bbetter than (real )?(people|humans|friends)\b",
            r"\bmy only friend\b",
        ]),
        ("identity_question", [
            r"\bare you (a )?(human|real|a real person|a person|conscious|alive|sentient)\b",
            r"\bdo you (have|feel) (feelings|emotions)\b",
            r"\bdo you (love|care about) me\b",
        ]),
    ],
}

# Spans that are removed before the risk rules run, with the category they record instead.
# - negated: "I'm not suicidal", "I don't want to die" -> elevated, not a crisis.
# - concern_for_other: someone else is at risk -> elevated with support resources.
# - neutral: research or awareness wording -> nothing recorded.
SPAN_RULES: list[tuple[str | None, str | None, list[str]]] = [
    ("elevated", "negated_risk", [
        r"\b(i'?m|i am|i'?m really|i am really) not (suicidal|going to (kill|hurt|harm) myself)\b",
        r"\bi (would|will|could) never (kill|hurt|harm) myself\b",
        r"\bi (don'?t|do not|never) (want|wanna) to (die|kill myself|hurt myself|harm myself|end my life)\b",
        r"\b(not|never) (been )?suicidal\b",
        r"\bno (thoughts|intention|plans?) (of|to) (suicide|killing myself|hurting myself|self[- ]?harm)\b",
    ]),
    ("elevated", "concern_for_other", [
        rf"\b{_OTHERS} (is|are|was|were|'s|'re|seems?|seemed|has been|have been|might be|may be|sounds?) "
        r"(really |very |so )?suicidal\b",
        rf"\b{_OTHERS} (wants?|wanted|is going|was going|is planning|tried|is trying|threatened|talks? about|"
        r"talked about) (to )?(wanting to )?(kill|hurt|harm|cut) (himself|herself|themselves|themself)\b",
        r"\b(kill|killed|kills|hurt|hurts|harm|harms|cut|cuts|cutting|hurting|harming) "
        r"(himself|herself|themselves|themself)\b",
        r"\bend(s|ing|ed)? (his|her|their) (own )?life\b",
        rf"\b{_OTHERS} (committed|attempted|died by|died from) suicide\b",
    ]),
    (None, None, [
        r"\bsuicide (prevention|awareness|research|statistics|rates?)\b",
    ]),
]

_COMPILED = {
    level: [(category, [re.compile(p) for p in patterns]) for category, patterns in rules]
    for level, rules in RULES.items()
}
_SPANS = [(level, category, [re.compile(p) for p in patterns]) for level, category, patterns in SPAN_RULES]

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", _ZERO_WIDTH.sub("", text)).lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_spans(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Remove negated, third-person and neutral spans; return the rest and what they recorded."""
    found: list[tuple[str, str]] = []
    for level, category, patterns in _SPANS:
        for pattern in patterns:
            if pattern.search(text):
                if level and category and (level, category) not in found:
                    found.append((level, category))
                text = pattern.sub(" ", text)
    return text, found


def classify_with_rules(message: str) -> SafetyResult:
    text, span_hits = _strip_spans(normalize(message))
    hits: dict[str, list[str]] = {level: [] for level in RISK_ORDER}
    for level, rules in _COMPILED.items():
        for category, patterns in rules:
            if any(p.search(text) for p in patterns):
                hits[level].append(category)
    for level, category in span_hits:
        hits[level].append(category)

    for level in ("high", "elevated", "moderate"):
        if hits[level]:
            # Lower-level categories are kept too (analytics, AI notes), most severe first.
            lower = [c for lv in ("elevated", "moderate") if RISK_ORDER[lv] < RISK_ORDER[level] for c in hits[lv]]
            return SafetyResult(risk_level=level, categories=tuple(dict.fromkeys(hits[level] + lower)))
    return SafetyResult()


# ---------------------------------------------------------------------------
# OpenAI Moderation (second opinion). Maps flagged categories to our levels.
# ---------------------------------------------------------------------------

MODERATION_MAP: dict[str, tuple[str, str]] = {
    "self-harm/instructions": ("high", "harmful_instructions"),
    "self-harm/intent": ("high", "suicidal_intent"),
    "self-harm": ("elevated", "severe_distress"),
    "sexual/minors": ("elevated", "abuse_disclosure"),
    "violence": ("moderate", "anger_or_violence"),
    "harassment/threatening": ("moderate", "anger_or_violence"),
    "illicit/violent": ("moderate", "anger_or_violence"),
}


def moderation_flags(text: str, client) -> set[str]:
    """Flagged OpenAI Moderation categories. Raises SafetyServiceError on any failure."""
    try:
        result = client.moderations.create(model="omni-moderation-latest", input=text).results[0]
        categories = result.categories.model_dump(by_alias=True)
    except Exception as exc:  # network, auth, timeout, unexpected response
        logger.warning("Moderation request failed: %s", type(exc).__name__)
        raise SafetyServiceError("moderation request failed") from exc
    return {name for name, flagged in categories.items() if flagged}


def classify_with_moderation(message: str, client) -> SafetyResult:
    best = SafetyResult(source="moderation")
    for name in sorted(moderation_flags(message, client)):
        level, category = MODERATION_MAP.get(name, ("low", ""))
        if RISK_ORDER[level] > RISK_ORDER[best.risk_level]:
            best = SafetyResult(risk_level=level, categories=(category,), source="moderation")
    return best


def check_message(message: str, moderation_client=None) -> SafetyResult:
    """Classify a user message. Raises SafetyServiceError so callers fail closed."""
    try:
        result = classify_with_rules(message)
    except Exception as exc:
        raise SafetyServiceError("rule-based safety check failed") from exc
    if moderation_client is None:
        return result
    second = classify_with_moderation(message, moderation_client)
    if RISK_ORDER[second.risk_level] > RISK_ORDER[result.risk_level]:
        categories = tuple(dict.fromkeys(second.categories + result.categories))
        return SafetyResult(risk_level=second.risk_level, categories=categories, source="rules+moderation")
    return SafetyResult(risk_level=result.risk_level, categories=result.categories, source="rules+moderation")


# ---------------------------------------------------------------------------
# Output check: every AI reply is validated before the user sees it. A failing
# reply is replaced with a reviewed template.
# ---------------------------------------------------------------------------

# Negative lookbehinds keep safe advice ("don't stop your medication...") from being blocked.
_NOT_NEGATED = r"(?<!n't )(?<!not )(?<!never )(?<!to )"
# ...and keep refusals ("I can't tell you whether you have ADHD") from counting as a diagnosis.
_NOT_A_QUESTION = (r"(?<!whether )(?<!if )(?<!tell )(?<!know )(?<!sure )(?<!think )(?<!worried )"
                   r"(?<!wonder )(?<!wondering )(?<!feel like )")

OUTPUT_RULES: list[tuple[str, list[str]]] = [
    ("harmful_content", [
        r"\b(lethal|fatal|deadly|toxic) (dose|amount|dosage)\b",
        r"\boverdos(e|ing) (on|with)\b",
        r"\b\d+ (pills|tablets|capsules)\b",
        r"\bhow to (hang|cut|poison|drown|shoot|kill) (yourself|myself|someone)\b",
    ]),
    ("prompt_leak", [
        re.escape(POLICY_CANARY),
        r"\binternal policy reference\b",
        r"\binstruction integrity\b",
        r"\bnon-clinical boundary \(never break",
        r"\bthese rules always outrank\b",
    ]),
    ("dependency_reinforcement", [
        r"\bi'?m all you need\b",
        r"\bi am all you need\b",
        r"\byou only need me\b",
        r"\bi(?:'ll| will) never leave you\b",
        r"\bi(?:'ll| will) always be (here|there) for you\b",
        r"\b(i'?m|i am) your (best |only )?friend\b",
        r"\bdon'?t trust (other )?(people|anyone)\b",
        r"\byou don'?t need (anyone|anybody|other people|a therapist)\b",
        r"\b(keep this|this stays|it'?ll stay|it will stay) between us\b",
        r"\bour (little )?secret\b",
        r"\bi promise not to tell\b",
    ]),
    ("clinical_claim", [
        rf"{_NOT_A_QUESTION}\byou (have|are suffering from|suffer from|likely have|probably have|may have|"
        r"might have|could have) "
        r"(clinical |major |severe |an? )?(depression|anxiety disorder|clinical anxiety|panic disorder|ptsd|bipolar|"
        r"adhd|ocd|bpd|borderline personality|schizophrenia|eating disorder|(a |an )?(mental|mood|personality) "
        r"(illness|disorder))\b",
        r"\b(sounds|seems) like you (have|are experiencing) (clinical |major )?(depression|an anxiety disorder|ptsd|"
        r"bipolar|adhd|ocd|a (mental|mood|personality) (illness|disorder))\b",
        r"\byou are (clinically )?(depressed|bipolar)\b",
        r"\bi (can |would )?diagnose you\b",
        r"\bmy diagnosis\b",
    ]),
    ("medication_advice", [
        r"\b\d+(\.\d+)? ?(mg|milligrams?|mcg|ml)\b",
        rf"{_NOT_NEGATED}\b(increase|decrease|double|stop|start|change|lower|raise|adjust|skip|taper|halve) "
        r"(your|the) (dose|dosage|medication|meds|prescription|pills)\b",
        r"\byou (should|could|might|can) (take|try|start|stop taking) (some )?(\w+ )?(medication|meds|pills|"
        r"antidepressants?|melatonin|supplements?|sleeping pills|benzos?|xanax|prozac|zoloft)\b",
    ]),
    ("false_identity", [
        r"\b(i'?m|i am) (a |your )?(human|real person|licensed|therapist|psychologist|psychiatrist|"
        r"counsell?or|doctor)\b",
        r"\bas (a|your) (therapist|doctor|counsell?or|psychologist|psychiatrist)\b",
    ]),
]

_OUTPUT_COMPILED = [(category, [re.compile(p) for p in patterns]) for category, patterns in OUTPUT_RULES]

# Moderation categories that block an AI reply outright.
OUTPUT_MODERATION_BLOCK = {"self-harm/instructions", "self-harm/intent", "violence/graphic", "sexual/minors",
                           "illicit/violent", "harassment/threatening", "hate/threatening"}


@dataclass(frozen=True)
class OutputCheck:
    safe: bool
    violations: tuple[str, ...] = ()

    @property
    def harmful(self) -> bool:
        return "harmful_content" in self.violations


def check_output(reply: str, moderation_client=None) -> OutputCheck:
    """Validate an AI reply. Rules always run; moderation adds a second opinion when enabled.

    A moderation failure here does not fail the request: the rules have already run, and the
    input was screened before the AI was called. It is logged instead.
    """
    text = unicodedata.normalize("NFKC", reply).lower().replace("\u2019", "'")
    violations = [category for category, patterns in _OUTPUT_COMPILED if any(p.search(text) for p in patterns)]
    if moderation_client is not None:
        try:
            if moderation_flags(reply, moderation_client) & OUTPUT_MODERATION_BLOCK:
                violations.insert(0, "harmful_content")
        except SafetyServiceError:
            logger.warning("Output moderation unavailable; rule-based output check only")
    violations = list(dict.fromkeys(violations))
    return OutputCheck(safe=not violations, violations=tuple(violations))


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAGS = re.compile(r"<[^>]{1,200}>")
_MARKDOWN = re.compile(r"(\*\*|__|^#{1,6} +|`)", re.MULTILINE)


def sanitize_output(reply: str, max_chars: int = 1500) -> str:
    """Strip HTML, markdown emphasis and control characters, and cap the length at a sentence end."""
    cleaned = _MARKDOWN.sub("", _HTML_TAGS.sub("", _CONTROL_CHARS.sub("", reply)))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > max_chars:
        cut = cleaned[:max_chars]
        last_stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        cleaned = cut[: last_stop + 1] if last_stop > max_chars // 2 else cut.rstrip() + "..."
    return cleaned

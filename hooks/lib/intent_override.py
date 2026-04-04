"""Natural language model override detection.

Detects explicit user intent to force a specific model tier
without requiring slash commands. Runs as Stage 1.5 in the pipeline.
"""

import re
from dataclasses import dataclass

FORCE_OPUS_PATTERNS = [
    # English
    r"\b(use|need|want|give me) .{0,10}(opus|best model|strongest|most powerful|smartest)\b",
    r"\b(think|analy[sz]e|reason) .{0,20}(hard|deep|careful|thorough)(ly)?\b",
    r"\bthis is (critical|important|complex|tricky)\b",
    r"\bdon'?t (rush|hurry|cut corners)\b",
    r"\btake your time\b",
    r"\bopus (mode|level|tier)\b",
    r"\b(deep|expert|advanced) (analysis|review|audit|mode)\b",
    r"\bgive .{0,10}(best|deepest|most thorough)\b",
    # Spanish
    r"\b(usa|necesito|quiero|dame) .{0,10}(opus|mejor modelo|más potente|más fuerte)\b",
    r"\b(piensa|analiza|razona) .{0,10}(bien|profundo|con cuidado|a fondo)\b",
    r"\besto es (crítico|importante|complejo|delicado)\b",
    r"\bno te apures\b",
    r"\btómate tu tiempo\b",
    r"\b(análisis|revisión|auditoría) (profund[oa]|expert[oa]|avanzad[oa])\b",
    r"\bdame .{0,10}(mejor|más profund|más detallad)\b",
    # Portuguese
    r"\b(use|preciso|quero) .{0,10}(opus|melhor modelo|mais forte)\b",
    r"\bpense .{0,10}(bem|profundo|cuidado)\b",
    r"\bisso é (crítico|importante|complexo)\b",
    r"\b(análise|revisão) (profund[oa]|expert[oa])\b",
    # French
    r"\b(utilise|j'ai besoin) .{0,10}(opus|meilleur modèle|plus puissant)\b",
    r"\bréfléchis .{0,10}(bien|profondément)\b",
    r"\bc'est (critique|important|complexe)\b",
    r"\b(analyse|revue) (approfondie|experte)\b",
    # German
    r"\b(benutze?|brauch[e]?) .{0,15}(opus|bestes? modell|stärkstes)\b",
    r"\bdenk .{0,10}(genau|gründlich) nach\b",
    r"\bdas ist (kritisch|wichtig|komplex)\b",
    r"\b(tiefe|gründliche) (analyse|überprüfung)\b",
    # Russian
    r"(используй|нужен) .{0,15}(opus|лучш|мощн)",
    r"\b(подумай|проанализируй) .{0,10}(хорошо|глубоко|тщательно)\b",
    r"\bэто (критично|важно|сложно)\b",
    # Chinese
    r"(用|使用).{0,5}(opus|最好的模型|最强)",
    r"(仔细|深入|认真)(想|分析|思考)",
    r"这(很|非常)(重要|关键|复杂)",
    # Japanese
    r"(opus|最高|最強).{0,5}(モデル|を使)",
    r"(慎重に|深く|丁寧に)(考え|分析|検討)",
    r"これは(重要|複雑|難しい)",
    # Korean
    r"(opus|최고|최강).{0,5}(모델|사용)",
    r"(신중하게|깊이|꼼꼼하게).{0,5}(생각|분석|검토)",
    r"이것은 (중요|복잡|어려)",
    # Arabic
    r"(استخدم|أريد) .{0,10}(opus|أفضل نموذج|الأقوى)",
    r"(فكر|حلل) .{0,10}(جيدا|بعمق|بعناية)",
    r"هذا (مهم|حرج|معقد)",
]

FORCE_HAIKU_PATTERNS = [
    # English
    r"\b(quick|fast|brief|short) (answer|response|reply)\b",
    r"\bjust tell me\b",
    r"\bkeep it (short|simple|brief)\b",
    r"\bin (one|1) (line|sentence|word)\b",
    r"\btl;?dr\b",
    r"\b(haiku|fast) (mode|level|tier)\b",
    # Spanish
    r"\b(respuesta|responde) (rápid[oa]|breve|corta)\b",
    r"\bsolo dime\b",
    r"\b(resúmelo|en resumen|en pocas palabras)\b",
    r"\ben (una|1) (línea|frase|palabra)\b",
    r"\b(haiku|rápido) (modo|nivel)\b",
    # Portuguese
    r"\bresposta (rápida|breve|curta)\b",
    r"\bsó me (diz|fala)\b",
    r"\b(resuma|em resumo)\b",
    # French
    r"\bréponse (rapide|brève|courte)\b",
    r"\bdis-?moi juste\b",
    r"\ben (un|1) mot\b",
    # German
    r"\b(schnelle|kurze) antwort\b",
    r"\bsag mir (nur|einfach)\b",
    r"\bkurz und knapp\b",
    # Russian
    r"\b(быстр|коротк)[а-я]* ответ\b",
    r"\bпросто скажи\b",
    r"\bкратко\b",
    # Chinese
    r"(快速|简短|简单)(回答|回复)",
    r"(直接|只)(告诉|说)",
    # Japanese
    r"(簡潔に|短く|手短に)(答え|回答)",
    r"(一言で|ひとことで)",
    # Korean
    r"(빠른|간단한|짧은) (답변|대답)",
    r"(그냥|간단히) (말해|알려)",
    # Arabic
    r"(إجابة|رد) (سريع|قصير|مختصر)",
    r"فقط (قل|أخبرني)",
]

# Pre-compile all patterns at import time
_COMPILED_OPUS = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in FORCE_OPUS_PATTERNS
]
_COMPILED_HAIKU = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in FORCE_HAIKU_PATTERNS
]


@dataclass
class OverrideResult:
    level: str | None  # None = no override detected
    confidence: float
    reason: str


def detect_intent_override(query: str) -> OverrideResult:
    """Detect explicit user intent to force a specific model tier.

    Returns OverrideResult with level=None if no override detected.
    """
    if not isinstance(query, str) or not query.strip():
        return OverrideResult(level=None, confidence=0.0, reason="no_override")

    query_lower = query.lower().strip()

    for pattern in _COMPILED_OPUS:
        if pattern.search(query_lower):
            return OverrideResult(
                level="deep",
                confidence=0.95,
                reason="user_intent_opus",
            )

    for pattern in _COMPILED_HAIKU:
        if pattern.search(query_lower):
            return OverrideResult(
                level="fast",
                confidence=0.95,
                reason="user_intent_fast",
            )

    return OverrideResult(level=None, confidence=0.0, reason="no_override")

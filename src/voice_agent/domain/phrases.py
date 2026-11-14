"""Every fixed sentence the system speaks, in one place.

Acknowledgements rotate so repeated lookups in one call never sound robotic."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phrases:
    greeting: str = 'أهلاً وسهلاً بك، معك المساعد الصوتي لخدمات كاك بنك. كيف أقدر أخدمك اليوم؟'
    small_talk: str = 'أهلاً بك، الحمد لله بخير. تفضّل، كيف أقدر أخدمك؟'
    acknowledgements: tuple[str, ...] = field(default_factory=lambda: (
        'تمام، لحظة من فضلك أراجع لك المعلومة.',
        'حاضر، خلّيني أتأكد لك من التفاصيل.',
        'سؤال مهم، ثواني وأفيدك.',
        'أكيد، أراجع لك المعلومات المعتمدة الآن.',
    ))
    still_working: str = 'ما زلت أراجع لك المعلومة، شكراً لصبرك، لحظات وأفيدك.'
    lookup_failed: str = 'أعتذر منك، ما قدرت أوصل للمعلومة حالياً. ممكن تعيد سؤالك بعد لحظات؟'
    clarify_fallback: str = 'حتى أفيدك بدقة، ممكن توضح لي طلبك أكثر؟'
    cancelled: str = 'تمام، توقفت عن انتظار الإجابة. كيف أقدر أساعدك؟'
    no_pending_lookup: str = 'ما عندي بحث جارٍ الآن. كيف أقدر أساعدك؟'
    away: str = 'أنا معك، خذ وقتك. إذا احتجت مساعدة أنا أسمعك.'

    @property
    def acknowledge(self) -> str:  # kept for callers that want a single phrase
        return self.acknowledgements[0]


DEFAULT_PHRASES = Phrases()

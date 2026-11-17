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
    # -- darai mode: DarAI answers; these only cover what it cannot say itself --
    #: Spoken once when a reply is taking a moment. Short, and rotated.
    fillers: tuple[str, ...] = field(default_factory=lambda: (
        'تمام.',
        'طيب.',
        'حاضر.',
        'أكيد.',
        'لحظة.',
        'خلني أشوف.',
        'ثواني بس.',
        'تمام، لحظة.',
    ))
    correction: str = 'عفواً، للتوضيح:'
    turn_failed: str = 'أعتذر منك، حصل خلل بسيط. ممكن تعيد ما قلته؟'
    no_reply: str = 'وصلتني رسالتك. إذا ما سمعت رداً، ممكن تعيد طلبك؟'
    #: The assistant is not answering this conversation: it is with the team.
    with_team: str = 'وصلت رسالتك لفريقنا، وسيتابع معك أحد الموظفين في أقرب وقت.'
    call_limit: str = 'وصلنا للحد الأقصى لمدة المكالمة. شكراً لتواصلك، ويمكنك الاتصال مرة أخرى في أي وقت.'
    #: Used until the channel's own greeting comes from DarAI.
    neutral_greeting: str = 'أهلاً وسهلاً بك. كيف أقدر أخدمك اليوم؟'

    @property
    def acknowledge(self) -> str:  # kept for callers that want a single phrase
        return self.acknowledgements[0]


DEFAULT_PHRASES = Phrases()

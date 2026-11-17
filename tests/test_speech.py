from voice_agent.domain.speech import spoken_text


def test_spoken_formatting_preserves_all_options_amounts_and_conditions():
    answer = "# كشف الحساب\n- **التطبيق**: الرسوم ١٢٫٥٠ ريال.\n- الفرع: 20 USD.\n- خدمة العملاء: متاحة إذا اكتمل التحقق."
    assert spoken_text(answer) == (
        "كشف الحساب\nالتطبيق: الرسوم ١٢٫٥٠ ريال.\nالفرع: 20 USD.\n"
        "خدمة العملاء: متاحة إذا اكتمل التحقق."
    )


def test_identifiers_negative_amounts_and_urls_are_unchanged():
    answer = "الرصيد -12.50، المرجع 001234، https://example.com/a_b، 1. الخيار الأول."
    assert spoken_text(answer) == answer

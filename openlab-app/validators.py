from decimal import Decimal

from constants import (
    EXPERIMENT_BROWSER_OPTIONS,
    GENDER_OPTIONS,
    LISTENING_ENVIRONMENT_OPTIONS,
    LISTENING_DEVICE_OPTIONS,
    MUSIC_EXPERIENCE_OPTIONS,
    SD_ITEMS,
    SELECTION_REASON_OPTIONS,
    VOLUME_IMPRESSION_OPTIONS,
)


class FormValidator:
    """参加者フォームと SD 法フォームの検証を担当する。"""

    def validate_participant_form(self, form):
        age_raw = (form.get("age") or "").strip()
        gender = (form.get("gender") or "").strip() or None
        music_experience = (form.get("music_experience") or "").strip() or None
        music_experience_years_raw = (
            form.get("music_experience_years") or ""
        ).strip()
        music_experience_type = (form.get("music_experience_type") or "").strip()
        listening_environment = (
            form.get("listening_environment") or ""
        ).strip() or None
        listening_environment_note = ""
        experiment_browser = (form.get("experiment_browser") or "").strip() or None
        experiment_browser_note = ""
        listening_device = (form.get("listening_device") or "").strip() or None
        listening_device_note = ""
        consent_agreed = (form.get("consent_agreed") or "").strip()
        errors = []

        age = None
        if age_raw:
            age = self.safe_int(age_raw)
            if age is None or age < 0 or age > 120:
                errors.append("年齢は 0〜120 の整数で入力してください。")

        allowed_genders = {item["value"] for item in GENDER_OPTIONS}
        if gender and gender not in allowed_genders:
            errors.append("性別の値が不正です。")

        allowed_experience = {item["value"] for item in MUSIC_EXPERIENCE_OPTIONS}
        if not music_experience:
            errors.append("音楽経験の有無を選択してください。")
        elif music_experience not in allowed_experience:
            errors.append("楽器演奏などの音楽経験の値が不正です。")

        allowed_environments = {
            item["value"] for item in LISTENING_ENVIRONMENT_OPTIONS
        }
        if not listening_environment:
            errors.append("実験に使う端末・OSを選択してください。")
        elif listening_environment not in allowed_environments:
            errors.append("実験に使う端末・OSの値が不正です。")

        allowed_browsers = {item["value"] for item in EXPERIMENT_BROWSER_OPTIONS}
        if not experiment_browser:
            errors.append("実験に使うブラウザを選択してください。")
        elif experiment_browser not in allowed_browsers:
            errors.append("実験に使うブラウザの値が不正です。")

        allowed_devices = {item["value"] for item in LISTENING_DEVICE_OPTIONS}
        if not listening_device:
            errors.append("音楽を聴くときに使う機器を選択してください。")
        elif listening_device not in allowed_devices:
            errors.append("音楽を聴くときに使う機器の値が不正です。")

        music_experience_years = None
        if music_experience_years_raw:
            music_experience_years = self.safe_int(music_experience_years_raw)
            if (
                music_experience_years is None
                or music_experience_years < 0
                or music_experience_years > 80
            ):
                errors.append("音楽経験の年数は 0〜80 の整数で入力してください。")

        if len(music_experience_type) > 500:
            errors.append("音楽経験の内容は 500 文字以内で入力してください。")

        if music_experience == "yes":
            if music_experience_years is None:
                errors.append("音楽経験ありの場合は、経験年数を入力してください。")
            if not music_experience_type:
                errors.append("音楽経験ありの場合は、経験していた内容を入力してください。")
        elif music_experience in {"no", "no_answer"}:
            music_experience_years = None
            music_experience_type = ""

        if consent_agreed != "yes":
            errors.append("実験内容を確認し、参加に同意してください。")

        return (
            age,
            gender,
            music_experience,
            music_experience_years,
            music_experience_type,
            listening_environment,
            listening_environment_note,
            experiment_browser,
            experiment_browser_note,
            listening_device,
            listening_device_note,
            consent_agreed == "yes",
            errors,
        )

    def validate_volume_check_form(self, form):
        volume_impression = (form.get("practice_volume_impression") or "").strip()
        volume_level_raw = (form.get("practice_volume_level") or "").strip()
        errors = []

        allowed_impressions = {item["value"] for item in VOLUME_IMPRESSION_OPTIONS}
        if not volume_impression:
            errors.append("練習後の音量について、感じ方を選択してください。")
        elif volume_impression not in allowed_impressions:
            errors.append("練習後の音量の感じ方の値が不正です。")

        volume_level = None
        if volume_level_raw:
            volume_level = self.safe_int(volume_level_raw)
            if volume_level is None or volume_level < 0 or volume_level > 100:
                errors.append("音量レベルは 0〜100 の整数で入力してください。")

        return volume_impression, volume_level, errors

    def validate_rating_form(self, form):
        values = {}
        errors = []

        for item in SD_ITEMS:
            field_name = item["name"]
            value = self.safe_int(form.get(field_name))
            if value is None:
                errors.append(f"{item['left']} - {item['right']} は必須です。")
                continue
            if value < 1 or value > 7:
                errors.append(
                    f"{item['left']} - {item['right']} は 1〜7 の範囲で入力してください。"
                )
                continue
            values[field_name] = value

        return values, errors

    def validate_selection_form(self, form):
        selected_choices = []
        for value in form.getlist("selection_reason_choices"):
            normalized = (value or "").strip()
            if normalized:
                selected_choices.append(normalized)

        reason_note = ""
        errors = []
        allowed_choices = {
            option["value"]: option["label"] for option in SELECTION_REASON_OPTIONS
        }

        invalid_choices = [
            value for value in selected_choices if value not in allowed_choices
        ]
        if invalid_choices:
            errors.append("一番好きだったところを選んだ理由の選択肢が不正です。")

        deduplicated_choices = []
        for value in selected_choices:
            if value in allowed_choices and value not in deduplicated_choices:
                deduplicated_choices.append(value)
        selected_choices = deduplicated_choices

        if not selected_choices:
            errors.append("当てはまる理由を少なくとも 1 つ選択してください。")

        reason_parts = []
        if selected_choices:
            labels = [allowed_choices[value] for value in selected_choices]
            reason_parts.append(f"選択理由: {'、'.join(labels)}")
        return {
            "selected_choices": selected_choices,
            "note": reason_note,
            "serialized_reason": " / ".join(reason_parts),
            "errors": errors,
        }

    @staticmethod
    def safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def safe_decimal(value):
        try:
            decimal_value = Decimal(str(value))
            return decimal_value.quantize(Decimal("0.000001"))
        except (ArithmeticError, ValueError, TypeError):
            return None

    @staticmethod
    def _get_list(form, field_name):
        if hasattr(form, "getlist"):
            return [
                (value or "").strip()
                for value in form.getlist(field_name)
                if (value or "").strip()
            ]
        value = form.get(field_name, [])
        if isinstance(value, (list, tuple)):
            return [(item or "").strip() for item in value if (item or "").strip()]
        return [(value or "").strip()] if (value or "").strip() else []

    @staticmethod
    def _deduplicate_values(values):
        deduplicated = []
        for value in values:
            if value not in deduplicated:
                deduplicated.append(value)
        return deduplicated

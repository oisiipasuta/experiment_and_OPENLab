import base64
import hashlib
import hmac
import secrets
import unicodedata
from datetime import timedelta

from flask import current_app

from models import ParticipantCredential, ResumeAttempt, db, utcnow


class CredentialService:
    """CloudWorks識別子、再開コード、完了コードを生値を残さず扱う。"""

    RESUME_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    MAX_RESUME_FAILURES = 5
    RESUME_WINDOW_MINUTES = 15

    @staticmethod
    def normalize_worker_id(value):
        normalized = unicodedata.normalize("NFKC", value or "").strip()
        if not normalized:
            raise ValueError("CloudWorksワーカーIDを入力してください。")
        if len(normalized) > 100:
            raise ValueError("CloudWorksワーカーIDは100文字以内で入力してください。")
        return normalized

    @staticmethod
    def _digest(value, config_key):
        secret = current_app.config[config_key].encode("utf-8")
        return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def hash_worker_id(self, worker_id):
        return self._digest(self.normalize_worker_id(worker_id), "WORKER_ID_PEPPER")

    def hash_resume_code(self, resume_code):
        normalized = unicodedata.normalize("NFKC", resume_code or "").strip().upper()
        return self._digest(normalized, "RESUME_CODE_SECRET")

    def hash_ip(self, ip_address):
        return self._digest(ip_address or "unknown", "WORKER_ID_PEPPER")

    @classmethod
    def generate_resume_code(cls):
        return "".join(secrets.choice(cls.RESUME_ALPHABET) for _ in range(12))

    def create_credential(self, participant, worker_id, resume_code):
        worker_hash = self.hash_worker_id(worker_id)
        normalized_resume = unicodedata.normalize(
            "NFKC", resume_code or ""
        ).strip().upper()
        if (
            len(normalized_resume) != 12
            or any(character not in self.RESUME_ALPHABET for character in normalized_resume)
        ):
            raise ValueError("再開コードを発行できませんでした。参加者情報画面を開き直してください。")
        if ParticipantCredential.query.filter_by(worker_id_hash=worker_hash).first():
            raise ValueError(
                "このCloudWorksワーカーIDでは既に参加記録があります。トップ画面の途中再開を利用してください。"
            )
        credential = ParticipantCredential(
            participant=participant,
            worker_id_hash=worker_hash,
            resume_code_hash=self.hash_resume_code(normalized_resume),
        )
        db.session.add(credential)
        return credential

    def resume_participant(self, worker_id, resume_code, ip_address):
        worker_hash = self.hash_worker_id(worker_id)
        ip_hash = self.hash_ip(ip_address)
        window_start = utcnow() - timedelta(minutes=self.RESUME_WINDOW_MINUTES)
        failed_count = ResumeAttempt.query.filter(
            ResumeAttempt.worker_id_hash == worker_hash,
            ResumeAttempt.ip_hash == ip_hash,
            ResumeAttempt.was_successful.is_(False),
            ResumeAttempt.attempted_at >= window_start,
        ).count()
        if failed_count >= self.MAX_RESUME_FAILURES:
            raise ValueError("再開の試行回数が上限に達しました。15分後にもう一度お試しください。")

        credential = ParticipantCredential.query.filter_by(
            worker_id_hash=worker_hash
        ).first()
        success = bool(
            credential
            and hmac.compare_digest(
                credential.resume_code_hash,
                self.hash_resume_code(resume_code),
            )
        )
        db.session.add(
            ResumeAttempt(
                worker_id_hash=worker_hash,
                ip_hash=ip_hash,
                was_successful=success,
            )
        )
        db.session.commit()
        return credential.participant if success else None

    def completion_code(self, participant):
        secret = current_app.config["COMPLETION_CODE_SECRET"].encode("utf-8")
        payload = f"completion:{participant.participant_id}".encode("utf-8")
        digest = hmac.new(secret, payload, hashlib.sha256).digest()
        token = base64.b32encode(digest).decode("ascii").rstrip("=")[:10]
        return f"CW-{token}"

    def issue_completion_code(self, participant):
        if participant.current_phase != "complete":
            raise ValueError("実験が完了していないため確認コードを発行できません。")
        if participant.credential and participant.credential.completion_issued_at is None:
            participant.credential.completion_issued_at = utcnow()
            db.session.commit()
        return self.completion_code(participant)

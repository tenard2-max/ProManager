"""7장 감시 지표 산출. 이력 로그로부터 재계산 가능."""

from __future__ import annotations

from typing import Any

from app.history.log import HistoryLog
from app.ini.status_store import StatusStore


class MetricsCalculator:
    def __init__(self, status_store: StatusStore, history: HistoryLog) -> None:
        self.status_store = status_store
        self.history = history

    def calculate(self) -> dict[str, Any]:
        doc = self.status_store.document
        events = self.history.read_all()
        from_state = self._from_status(doc)
        from_history = self._from_history(events, doc)
        # 상태 기반 + 이력 기반 병합 (이력에 더 풍부한 이벤트 지표)
        return {**from_state, **from_history, "source": "live"}

    def recalculate_from_history(self) -> dict[str, Any]:
        doc = self.status_store.document
        events = self.history.read_all()
        result = {**self._from_status(doc), **self._from_history(events, doc)}
        result["source"] = "history_recalc"
        return result

    def _from_status(self, doc: Any) -> dict[str, Any]:
        if doc is None or not doc.items:
            return {
                "first_pass_rate": None,
                "avg_rework_count": 0.0,
                "self_report_deviation": None,
                "judgment_consistency": None,
                "defect_hit_rate": None,
                "avg_command_ack_ms": None,
                "requirement_fulfillment_rate": 0.0,
                "total_items": 0,
                "verified_count": 0,
            }

        items = list(doc.items.values())
        total = len(items)
        verified = sum(1 for i in items if i.status == "VERIFIED")
        avg_rework = sum(i.qa_rework_count for i in items) / total

        # 첫 검증 합격률: 재작업 0이고 PASSED/VERIFIED인 항목 / QA 수행 항목
        qa_done = [
            i
            for i in items
            if i.qa_status in ("PASSED", "FAILED_REWORK") or i.status == "VERIFIED"
        ]
        first_pass = [
            i
            for i in qa_done
            if i.qa_rework_count == 0 and i.qa_status == "PASSED"
        ]
        # VERIFIED이면서 rework 0도 첫 합격으로 간주
        first_pass_verified = [
            i for i in items if i.status == "VERIFIED" and i.qa_rework_count == 0
        ]
        first_pass_set = {i.req_id for i in first_pass} | {
            i.req_id for i in first_pass_verified
        }
        first_pass_rate = (
            len(first_pass_set) / len(qa_done) if qa_done else None
        )

        # 자기보고 편차: Cursor 상한 60과 QA 최종 progress 차이 (QA 완료 항목)
        deviations = []
        for i in items:
            if i.qa_status == "PASSED" or i.status == "VERIFIED":
                deviations.append(abs(60 - i.progress))
        self_report_deviation = (
            round(sum(deviations) / len(deviations), 2) if deviations else None
        )

        return {
            "first_pass_rate": (
                round(first_pass_rate, 4) if first_pass_rate is not None else None
            ),
            "avg_rework_count": round(avg_rework, 4),
            "self_report_deviation": self_report_deviation,
            "requirement_fulfillment_rate": round(verified / total, 4),
            "total_items": total,
            "verified_count": verified,
        }

    def _from_history(
        self, events: list[dict[str, Any]], doc: Any
    ) -> dict[str, Any]:
        # 판정 일관성: 동일 req_id에 대한 연속 QA 판정 일치율
        qa_by_req: dict[str, list[str]] = {}
        for ev in events:
            if ev.get("event_type") != "message_handled":
                continue
            payload = ev.get("payload") or {}
            if payload.get("type") != "QA_RESULT":
                continue
            result = payload.get("result") or {}
            req_id = result.get("req_id")
            qa_status = result.get("qa_status")
            if req_id and qa_status:
                qa_by_req.setdefault(req_id, []).append(qa_status)

        consistent = 0
        pairs = 0
        for statuses in qa_by_req.values():
            for a, b in zip(statuses, statuses[1:]):
                pairs += 1
                if a == b:
                    consistent += 1
        judgment_consistency = (
            round(consistent / pairs, 4) if pairs else None
        )

        # 결함 적중률: extra_verify 이후 FAILED_REWORK가 나온 비율
        extra_verify_reqs: set[str] = set()
        defect_hits: set[str] = set()
        for ev in events:
            et = ev.get("event_type")
            payload = ev.get("payload") or {}
            if et == "command_submitted" and payload.get("command_type") == "extra_verify":
                for rid in payload.get("req_ids") or []:
                    extra_verify_reqs.add(rid)
            if et == "message_handled" and payload.get("type") == "QA_RESULT":
                result = payload.get("result") or {}
                if (
                    result.get("req_id") in extra_verify_reqs
                    and result.get("qa_status") == "FAILED_REWORK"
                ):
                    defect_hits.add(result["req_id"])

        defect_hit_rate = (
            round(len(defect_hits) / len(extra_verify_reqs), 4)
            if extra_verify_reqs
            else None
        )

        # 명령 응답 시간
        latencies = [
            ev["payload"]["ack_latency_ms"]
            for ev in events
            if ev.get("event_type") == "command_ack"
            and (ev.get("payload") or {}).get("ack_latency_ms") is not None
        ]
        avg_command_ack_ms = (
            round(sum(latencies) / len(latencies), 2) if latencies else None
        )

        return {
            "judgment_consistency": judgment_consistency,
            "defect_hit_rate": defect_hit_rate,
            "avg_command_ack_ms": avg_command_ack_ms,
        }

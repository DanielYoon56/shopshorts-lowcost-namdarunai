"""OCR 엔진 없이 규칙 기반 추출만 검증 (실제 쿠팡 상세 이미지 OCR 결과를 입력으로 사용)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from coupang_ocr import extract_specs, find_conflicts, to_research_context  # noqa: E402

# 전기매트 상세 이미지 10장의 실제 OCR 결과 일부 (2026-11-11)
LINES = [
    ("detail_00.png", ["TMC", "Attestation of Compliance", "C", "FC", "RoHS", "CE", "UKCA"]),
    ("detail_02.png", ["들어주는 9가지 기능", "9단계 온도 조절", "4단 타이밍:", "자동 전원 끄기", "물세탁 가능", "빠른 가열"]),
    ("detail_05.png", ["지능형 타이밍", "자동 전원 차단으로 더욱 안전함", "60", "30/60/90/120분타", "3초급속가열"]),
    ("detail_09.jpg", ["주문 시 개인통관고유부호 필수 입력", "변환플러그로 인한 문제는 반품사유가 되지 않습니다."]),
]
TITLE = "[CTK] 전기매트 미니 발열매트 고온찜질 히팅패드 온도조절 4단계 타이머설정 물세척 빠른발열 유럽형코드"


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.r = extract_specs(LINES)
        self.values = {(s["type"], s["value"]) for s in self.r["specs"]}

    def test_specs(self):
        self.assertIn(("단계 조절", "9단계 온도 조절"), self.values)
        self.assertIn(("단계 조절", "4단 타이밍"), self.values)
        self.assertIn(("시간/타이머", "30/60/90/120분"), self.values)
        self.assertIn(("가열/작동 시간", "3초급속가열"), self.values)

    def test_features_certs_notes(self):
        self.assertEqual({f["type"] for f in self.r["features"]}, {"자동 전원 차단", "물세탁 가능", "급속 가열"})
        self.assertEqual({c["type"] for c in self.r["certifications"]}, {"FCC", "RoHS", "CE", "UKCA"})
        notes = {n["type"] for n in self.r["purchase_notes"]}
        self.assertIn("해외직구 상품 (개인통관고유부호 필요)", notes)
        self.assertIn("변환 플러그 필요 가능성", notes)

    def test_evidence_kept(self):
        spec = next(s for s in self.r["specs"] if s["value"] == "9단계 온도 조절")
        self.assertEqual(spec["image"], "detail_02.png")

    def test_title_conflict_by_subject(self):
        conflicts = find_conflicts(TITLE, self.r["specs"])
        self.assertEqual(len(conflicts), 1)
        self.assertIn("온도 4단계", conflicts[0])
        self.assertIn("온도 9단계", conflicts[0])

    def test_no_conflict_when_consistent(self):
        self.assertEqual(find_conflicts("전기매트 온도조절 9단계", self.r["specs"]), [])

    def test_context_rules(self):
        ctx = to_research_context({**self.r, "conflicts": find_conflicts(TITLE, self.r["specs"])})
        self.assertIn("배송 속도 소구 금지", ctx)
        self.assertIn("[불일치 주의]", ctx)


if __name__ == "__main__":
    unittest.main()

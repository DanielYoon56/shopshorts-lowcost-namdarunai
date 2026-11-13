import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from coupang_crawler import (  # noqa: E402
    CrawlerError,
    parse_product_html,
    partners_authorization,
    read_saved_page,
    to_research_context,
)

# 2026-11 실제 쿠팡 상품 상세 저장본의 구조를 축약한 샘플
NEW_DOM = """<html><head>
<title>[CTK] 전기매트 미니 - 전기매트 | 쿠팡</title>
<link rel="canonical" href="https://www.coupang.com/vp/products/9165963614">
<meta property="og:image" content="//thumbnail.coupangcdn.com/thumbnails/remote/640x640ex/image/vendor_inventory/2064/main.jpeg">
<meta property="og:description" content="쿠팡에서 [CTK] 전기매트 미니 구매하고 더 많은 혜택을 받으세요!">
</head><body>
<ul class="breadcrumb twc-flex"><li><a>쿠팡 홈</a></li><li><a>홈인테리어</a><svg><path d="M1"/></svg></li><li><a>전기매트</a></li></ul>
<div class="prod-atf">
  <img class="thumbnail" src="https://thumbnail.coupangcdn.com/thumbnails/remote/120x120ex/image/vendor_inventory/2064/main.jpeg">
  <img class="thumbnail" src="https://thumbnail.coupangcdn.com/thumbnails/remote/120x120ex/image/retail/images/second.jpg">
  <div class="product-image">
    <img src="https://thumbnail.coupangcdn.com/thumbnails/remote/48x48ex/image/vendor_inventory/2064/main.jpeg">
    <img src="https://image.coupangcdn.com/image/mobile_app/v3/badges/thumbs_up/x.png">
  </div>
  <h1 class="product-title"><span>[CTK] 전기매트 미니</span></h1>
  <div class="review-atf"><span class="rating-star-container"><span class="rating-star-num" style="width: 90%; max-width: 100%;"></span></span>
  <span class="rating-count-txt">4 개 상품평</span></div>
  <div class="price-container false">
    <div class="sales-price"><div class="price-amount sales-price-amount"></div></div>
    <div class="final-price"><div class="price-amount final-price-amount">18,900원</div></div>
  </div>
  <span class="shipping-fee-desc"><em class="prod-txt-bold">무료배송</em></span>
  <div class="regular-pdd-container"><em>12/2</em><em> 도착 예정</em></div>
  <div class="seller-info"><div>판매자:<a href="#">씨티케이글로벌 유한회사<div>판매자 상품 보러가기</div></a></div>
    <div><span>판매자 평가</span><img src="https://image.coupangcdn.com/image/mobile_app/icon.png"><span>90%</span><span>(329)</span></div>
    <div>배송사: <span>CJ 대한통운</span></div></div>
  <div class="instant-option-v2"><section><div><span>사이즈: </span><span><span>30x60cm</span></span></div>
    <div><div><div>30x60cm</div></div><div><div>40x76cm</div><div><span>+2,000원</span></div></div>
    <div><div>43x84cm</div><div><span>일시품절</span></div></div></div></section></div>
  <div data-host="https://www.coupang.com/vp/products/9165963614?itemId=27006091139&amp;vendorItemId=94000000001&amp;traceid=x"></div>
</div>
<!-- 추천/광고 상품: 메인 값과 섞이면 안 됨 -->
<div class="promotion-item"><span class="origin-price">30,000원</span><span class="discount-rate">20%</span>
  <a href="https://www.coupang.com/vp/products/7935088564?itemId=19154803517&amp;vendorItemId=3068445128">광고</a>
  <h3 class="product-title">다른 상품</h3></div>
<div id="itemBrief"><table><tbody>
  <tr><td>품명 및 모델명</td><td>CTK-100</td><td>KC 인증정보</td><td>상품 상세페이지 참조</td></tr>
  <tr><td>브랜드</td><td>CTK</td></tr>
</tbody></table></div>
<div class="type-IMAGE_NO_SPACE"><div class="subType-IMAGE with-width-780">
  <img src="https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/vendor_inventory/35f0/d1.png"></div></div>
<div class="type-IMAGE_NO_SPACE"><div class="subType-IMAGE with-width-780">
  <img src="https://thumbnail.coupangcdn.com/thumbnails/remote/q89/image/vendor_inventory/726d/d2.png"></div></div>
</body></html>"""

# 구조화 데이터(JSON-LD)만 있는 페이지 (구버전/대체 경로)
LD_ONLY = """<html><head>
<link rel="canonical" href="https://www.coupang.com/vp/products/7777?itemId=11&vendorItemId=22&traceid=abc">
<script type="application/ld+json">
{"@type":"Product","name":"테스트 무선 이어폰","brand":{"name":"테스트브랜드"},
 "image":["https://thumbnail9.coupangcdn.com/a.jpg?t=1","https://evil.example/x.jpg"],
 "offers":{"price":"29900","priceCurrency":"KRW","availability":"https://schema.org/InStock"},
 "aggregateRating":{"ratingValue":"4.5","reviewCount":"1,234"}}
</script></head><body></body></html>"""


class NewDomTests(unittest.TestCase):
    def setUp(self):
        self.r = parse_product_html(NEW_DOM)
        self.f = self.r["fields"]

    def test_core_fields(self):
        self.assertEqual(self.f["title"], "[CTK] 전기매트 미니")
        self.assertEqual(self.f["sale_price"], 18900)
        self.assertEqual(self.f["rating"], "4.5")
        self.assertEqual(self.f["review_count"], 4)
        self.assertEqual(self.f["shipping"], "무료배송")
        self.assertEqual(self.f["arrival"], "12/2 도착 예정")
        self.assertEqual(self.f["brand"], "CTK")
        self.assertEqual(self.f["description"], "")  # 쿠팡 기본 SEO 문구는 버림

    def test_recommended_items_do_not_leak(self):
        self.assertIsNone(self.f["original_price"])
        self.assertEqual(self.f["discount_rate"], "")
        self.assertEqual(self.f["item_id"], "27006091139")
        self.assertEqual(self.f["vendor_item_id"], "94000000001")

    def test_seller(self):
        self.assertEqual(self.f["seller"], "씨티케이글로벌 유한회사")
        self.assertEqual(self.f["seller_rating"], "90% (329)")
        self.assertEqual(self.f["courier"], "CJ 대한통운")

    def test_options(self):
        self.assertEqual(self.f["options"], [
            {"group": "사이즈", "name": "30x60cm", "price_delta": 0, "sold_out": False},
            {"group": "사이즈", "name": "40x76cm", "price_delta": 2000, "sold_out": False},
            {"group": "사이즈", "name": "43x84cm", "price_delta": 0, "sold_out": True},
        ])

    def test_category_and_specs(self):
        self.assertEqual(self.f["category_path"], ["홈인테리어", "전기매트"])
        self.assertEqual(self.f["specs"][0], {"name": "품명 및 모델명", "value": "CTK-100"})
        self.assertEqual(len(self.f["specs"]), 3)

    def test_images(self):
        self.assertEqual(self.f["gallery_images"], [
            "https://thumbnail.coupangcdn.com/thumbnails/remote/640x640ex/image/vendor_inventory/2064/main.jpeg",
            "https://thumbnail.coupangcdn.com/thumbnails/remote/640x640ex/image/retail/images/second.jpg",
        ])
        self.assertEqual(len(self.f["detail_images"]), 2)

    def test_context(self):
        ctx = to_research_context(self.r)
        self.assertIn("18,900원", ctx)
        self.assertIn("사이즈: 40x76cm (+2,000원)", ctx)
        self.assertIn("43x84cm [품절]", ctx)
        self.assertNotIn("30,000", ctx)

    def test_mhtml(self):
        mhtml = (
            "From: <Saved by Blink>\r\nMIME-Version: 1.0\r\n"
            'Content-Type: multipart/related; boundary="B"\r\n\r\n'
            "--B\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
            + NEW_DOM + "\r\n--B--\r\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.mhtml"
            p.write_bytes(mhtml.encode("utf-8"))
            self.assertEqual(parse_product_html(read_saved_page(p))["fields"]["sale_price"], 18900)


class LdOnlyTests(unittest.TestCase):
    def test_json_ld_fallback(self):
        f = parse_product_html(LD_ONLY)["fields"]
        self.assertEqual(f["title"], "테스트 무선 이어폰")
        self.assertEqual(f["brand"], "테스트브랜드")
        self.assertEqual(f["sale_price"], 29900)
        self.assertEqual(f["review_count"], 1234)
        self.assertEqual(f["vendor_item_id"], "22")
        self.assertEqual(f["gallery_images"], ["https://thumbnail9.coupangcdn.com/a.jpg"])

    def test_access_denied_rejected(self):
        with self.assertRaises(CrawlerError):
            parse_product_html("<html><title>Access Denied</title></html>")


class PartnersTests(unittest.TestCase):
    def test_signature_format(self):
        now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        auth = partners_authorization("GET", "/v2/x", "keyword=a", "AK", "SK", now)
        self.assertTrue(auth.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=260102T030405Z, signature="))
        self.assertEqual(len(auth.rsplit("=", 1)[1]), 64)


if __name__ == "__main__":
    unittest.main()

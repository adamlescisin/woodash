from app.transform import attribution, channel_of, cost_of, customer_key, order_lines

ORDER = {
    "id": 101, "status": "completed", "created_via": "woocommerce-pos", "customer_id": 0,
    "date_created_gmt": "2026-10-09T13:30:00", "billing": {"email": "Test@Example.com"},
    "meta_data": [{"key": "_wc_order_attribution_utm_source", "value": "facebook"},
                  {"key": "_wc_order_attribution_utm_medium", "value": "paid"}],
    "line_items": [
        {"id": 1, "product_id": 10, "variation_id": 11, "quantity": 2, "subtotal": "1000", "total": "900", "sku": "A-1"},
        {"id": 2, "product_id": 20, "variation_id": 0, "quantity": 1, "subtotal": "500", "total": "500", "sku": ""},
    ],
}


def test_lines_use_local_time_and_pos_channel():
    lines = order_lines(ORDER, "Europe/Prague")
    assert [l["variant_id"] for l in lines] == [11, 20]
    assert lines[0]["hour"] == 15 and str(lines[0]["date"]) == "2026-10-09"  # 13:30 UTC = 15:30 CEST
    assert lines[0]["channel"] == "store"
    assert lines[0]["net_revenue"] == 900 and lines[0]["discount"] == 100
    assert (lines[0]["source"], lines[0]["medium"], lines[0]["campaign"]) == ("facebook", "paid", None)


def test_refund_reduces_quantity_and_revenue():
    refunds = [{"line_items": [{"quantity": -1, "total": "-450", "meta_data": [{"key": "_refunded_item_id", "value": "1"}]}]}]
    lines = order_lines(ORDER, "Europe/Prague", refunds)
    assert lines[0]["qty"] == 1 and lines[0]["net_revenue"] == 450


def test_full_refund_drops_line_and_uncounted_status_drops_order():
    refunds = [{"line_items": [{"quantity": -1, "total": "-500", "meta_data": [{"key": "_refunded_item_id", "value": "2"}]}]}]
    assert [l["variant_id"] for l in order_lines(ORDER, "Europe/Prague", refunds)] == [11]
    assert order_lines({**ORDER, "status": "cancelled"}, "Europe/Prague") == []


def test_customer_key_is_case_insensitive_hash_without_email():
    a = customer_key(ORDER)
    assert a == customer_key({**ORDER, "billing": {"email": "test@example.com"}})
    assert isinstance(a, int) and "example" not in str(a)
    assert customer_key({"billing": {"email": ""}, "customer_id": 0}) is None
    assert customer_key({"billing": {}, "customer_id": 7}) == 7


def test_channel_and_attribution_defaults():
    assert channel_of({"created_via": "checkout"}) == "web"
    assert channel_of({"created_via": "point-of-sale"}) == "store"
    assert channel_of({"created_via": "admin", "meta_data": [{"key": "wc_pos_register_id", "value": "3"}]}) == "store"
    assert channel_of({"created_via": "admin", "meta_data": [{"key": "wc_pos_register_id", "value": "0"}]}) == "web"
    assert attribution({}) == (None, None, None)


def test_cost_meta_keys():
    item = {"meta_data": [{"key": "_cost", "value": "123,5"}]}
    assert cost_of(item) == 123.5
    assert cost_of(item, ("other",)) is None

"""Guard rail tests. Run: python -m pytest tests/ -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TTS_APP_SECRET", "x")
os.environ.setdefault("ADMIN_TOKEN", "t")
os.environ.setdefault("TOKEN_STORE_PATH", "/tmp/test_tokens.json")
import pytest
from app import assert_read_only, UnsafeCall

MUST_ALLOW = [
    "/finance/202309/statements", "/finance/202309/transactions",
    "/order/202309/orders/search", "/product/202309/products/search",
    "/affiliate_seller/202405/creators", "/affiliate_seller/202405/videos",
    "/analytics/202405/shop/performance", "/fulfillment/202309/packages",
    "/return_refund/202309/returns/search", "/return_refund/202309/refunds/search",
    "/authorization/202309/shops",
]
MUST_BLOCK = [
    "/product/202309/products/price/update", "/product/202309/inventory/update",
    "/product/202309/products/deactivate", "/product/202309/global_products/edit",
    "/order/202309/orders/cancel", "/order/202309/fulfillments/ship",
    "/return_refund/202309/refunds/approve", "/return_refund/202309/returns/reject",
    "/finance/202309/withdraw", "/promotion/202309/activities/create",
    "/customer_service/202309/messages", "/seller/202309/shops/update",
]

@pytest.mark.parametrize("path", MUST_ALLOW)
def test_reporting_paths_allowed(path):
    assert_read_only("GET", path)

@pytest.mark.parametrize("path", MUST_BLOCK)
def test_mutating_paths_blocked(path):
    with pytest.raises(UnsafeCall):
        assert_read_only("GET", path)

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_non_get_methods_blocked(method):
    with pytest.raises(UnsafeCall):
        assert_read_only(method, "/finance/202309/statements")

def test_read_only_false_fails_closed(monkeypatch):
    import importlib, app
    monkeypatch.setenv("READ_ONLY", "false")
    importlib.reload(app)
    with pytest.raises(app.UnsafeCall):
        app.assert_read_only("GET", "/finance/202309/statements")

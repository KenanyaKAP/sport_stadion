"""MCP endpoint tests over raw JSON-RPC, the same way the Conversify app talks to /mcp."""

import re

import pytest

ACCOUNT = "rina@example.com"


class MCP:
    def __init__(self, client, email: str | None = ACCOUNT, host: str = "Kens-MacBook-Pro.local:8765"):
        self.client = client
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Host": host,
        }
        if email:
            self.headers["X-Customer-Email"] = email
        self._id = 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        r = self.client.post("/mcp", headers=self.headers, json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "error" not in body, body
        return body["result"]

    def call(self, tool: str, /, **arguments) -> tuple[str, bool]:
        result = self.rpc("tools/call", {"name": tool, "arguments": arguments})
        return result["content"][0]["text"], result.get("isError", False)

    def ok(self, tool: str, /, **arguments) -> str:
        text, is_error = self.call(tool, **arguments)
        assert not is_error, text
        return text

    def err(self, tool: str, /, **arguments) -> str:
        text, is_error = self.call(tool, **arguments)
        assert is_error, text
        return text


@pytest.fixture
def mcp(client):
    return MCP(client)


def stock(client, sku: str) -> int:
    return client.get(f"/api/variants/{sku}").json()["stock"]


def in_stock_variant(client, slug: str, min_stock: int = 3) -> dict:
    product = client.get(f"/api/products/{slug}").json()
    return next(v for v in product["variants"] if v["stock"] >= min_stock)


def test_handshake_and_tool_list(mcp):
    init = mcp.rpc("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"},
    })
    assert init["serverInfo"]["name"] == "Sport Stadion"
    assert "place_order" in init["instructions"]

    tools = {t["name"]: t for t in mcp.rpc("tools/list")["tools"]}
    assert set(tools) == {
        "search_products", "get_product_details", "get_size_guide", "add_to_cart", "view_cart",
        "update_cart_item", "apply_promo_code", "place_order", "get_order_status", "cancel_order",
    }
    assert tools["view_cart"]["annotations"]["readOnlyHint"] is True
    assert tools["cancel_order"]["annotations"]["destructiveHint"] is True
    for name in ("place_order", "cancel_order"):
        assert tools[name]["_meta"]["conversify/requiresConfirmation"] is True
    assert "conversify/requiresConfirmation" not in (tools["add_to_cart"].get("_meta") or {})
    # Compacted schemas: no pydantic titles or nullable anyOf noise
    assert "title" not in str(tools["search_products"]["inputSchema"])
    assert "anyOf" not in str(tools["place_order"]["inputSchema"])


def test_catalog_tools_are_lenient(mcp):
    text = mcp.ok("search_products", query="sepatu lari", color="black", size="eu 42")
    assert "velocita-aero-glide-3" in text

    text = mcp.ok("search_products", query="sepatu lari zzzz")
    assert "closest matches" in text

    details = mcp.ok("get_product_details", product="Aero Glide 3")  # partial name, not slug
    assert "Stock by colour" in details and "Hitam" in details

    ambiguous = mcp.err("get_product_details", product="aero glide")
    assert "several products" in ambiguous

    guide = mcp.ok("get_size_guide", product="velocita-aero-glide-3", foot_length_cm=26.4)
    assert "Recommended size: 42." in guide
    guide = mcp.ok("get_size_guide", product="kinetik-drycore-tee", chest_cm=96)
    assert "Recommended size: M." in guide


def test_full_order_flow(client, mcp):
    variant = in_stock_variant(client, "velocita-aero-glide-3")
    before = stock(client, variant["sku"])

    text = mcp.ok("add_to_cart", product="velocita-aero-glide-3", color=variant["color_name"].lower(),
                  size=f"EU {variant['size']}", quantity=2)
    assert "Added 2 ×" in text and "/cart?cart=" in text
    assert "http://Kens-MacBook-Pro.local:8765/cart" in text  # links use the host the app connected to

    # Same account from another chat room sees the same cart; another account doesn't.
    assert "Velocita Aero Glide 3" in MCP(client).ok("view_cart")
    assert MCP(client, email="other@example.com").ok("view_cart") == "The cart is empty."

    mcp.ok("add_to_cart", product="nordline-hydro-bottle", color="silver", size="1L")
    text = mcp.ok("update_cart_item", item_number=2, quantity=0)
    assert "Removed Nordline Hydro Bottle" in text

    assert "applied" in mcp.ok("apply_promo_code", code="stadion10")
    assert "invalid" in mcp.err("apply_promo_code", code="NOPE")

    missing = mcp.err("place_order", shipping_method="express", payment_method="bank_transfer", name="Rina")
    assert "Missing customer details" in missing and "postal_code" in missing

    bad = mcp.err("place_order", shipping_method="express", payment_method="bank_transfer", name="Rina",
                  phone="081234567890", street="Jl. Melati 5", city="Bandung", province="Jawa Barat", postal_code="40")
    assert "postal_code" in bad

    placed = mcp.ok("place_order", shipping_method="express", payment_method="bank_transfer", name="Rina Wijaya",
                    phone="081234567890", street="Jl. Melati 5", city="Bandung", province="Jawa Barat", postal_code="40115")
    number = re.search(r"SS-\d{8}-\d{5}", placed).group()
    assert "Virtual Account" in placed and f"/order/{number}" in placed
    assert stock(client, variant["sku"]) == before - 2
    assert mcp.ok("view_cart") == "The cart is empty."

    # Second order reuses the saved name/address.
    mcp.ok("add_to_cart", product="kinetik-run-cap", color="Hitam", size="one size")
    again = mcp.ok("place_order", shipping_method="pickup", payment_method="e_wallet")
    assert "reused" in again and "Rina Wijaya" in again

    assert number in mcp.ok("get_order_status")
    assert "pending_payment" in mcp.ok("get_order_status", order_number=number.lower())
    assert "not found" in MCP(client, email="other@example.com").err("get_order_status", order_number=number)

    assert "cancelled" in mcp.ok("cancel_order", order_number=number)
    assert stock(client, variant["sku"]) == before
    assert "cannot be cancelled" in mcp.err("cancel_order", order_number=number)


def test_helpful_errors(client, mcp):
    text = mcp.err("add_to_cart", product="velocita-aero-glide-3", color="Hitam", size="50")
    assert "Sizes in stock:" in text
    text = mcp.err("add_to_cart", product="velocita-aero-glide-3", color="purple", size="42")
    assert "Available colours: Hitam, Biru Navy, Oranye" in text
    assert "Use search_products" in mcp.err("get_product_details", product="flying carpet")
    assert "Unknown category" in mcp.err("search_products", category="snowboards")


def test_account_header_required_for_cart(client):
    anonymous = MCP(client, email=None)
    assert "Found" in anonymous.ok("search_products", query="raket")  # catalogue works without an account
    assert "X-Customer-Email" in anonymous.err("view_cart")
    assert "X-Customer-Email" in anonymous.err("add_to_cart", product="kinetik-run-cap", color="Hitam", size="One Size")


def test_info_advertises_mcp(client):
    assert client.get("/api/info").json()["mcp_endpoint"] == "/mcp"

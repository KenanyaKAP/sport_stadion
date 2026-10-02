# The `client` fixture (TestClient on a throwaway database) lives in conftest.py.

CUSTOMER = {"name": "Budi Santoso", "email": "budi@example.com", "phone": "+62 812 3456 7890"}
ADDRESS = {"street": "Jl. Sudirman No. 1", "city": "Jakarta Selatan", "province": "DKI Jakarta", "postal_code": "12190"}


def first_in_stock(client, slug):
    product = client.get(f"/api/products/{slug}").json()
    return next(v for v in product["variants"] if v["stock"] >= 2)


def test_catalog_listing_and_filters(client):
    all_products = client.get("/api/products", params={"page_size": 100}).json()
    assert all_products["total"] == 29

    shoes = client.get("/api/products", params={"category": "sepatu-lari"}).json()
    assert shoes["total"] > 0 and all(p["category_slug"] == "sepatu-lari" for p in shoes["items"])

    black_42 = client.get("/api/products", params={"color": "hitam", "size": "42"}).json()
    assert all("Hitam" in [c["name"] for c in p["colors"]] and "42" in p["sizes"] for p in black_42["items"])

    cheap = client.get("/api/products", params={"max_price": 200_000, "sort": "price_asc"}).json()
    prices = [p["price_min"] for p in cheap["items"]]
    assert prices == sorted(prices) and all(p <= 200_000 for p in prices)

    search = client.get("/api/products", params={"q": "futsal"}).json()
    assert any("futsal" in p["slug"] for p in search["items"])


def test_on_sale_and_scoped_facets(client):
    sale = client.get("/api/products", params={"on_sale": True, "page_size": 100}).json()
    assert sale["total"] == 6 and all(p["compare_at_price"] for p in sale["items"])

    all_facets = client.get("/api/facets").json()
    assert len(all_facets["categories"]) == 9 and all_facets["product_count"] == 29

    running = client.get("/api/facets", params={"category": "sepatu-lari"}).json()
    assert [c["slug"] for c in running["categories"]] == ["sepatu-lari"]
    assert {b["slug"] for b in running["brands"]} == {"velocita", "kinetik"}
    assert "M" not in running["sizes"] and "42" in running["sizes"]


def test_product_detail(client):
    p = client.get("/api/products/velocita-aero-glide-3").json()
    assert p["specs"]["Heel-to-toe drop"] == "8 mm"
    assert p["size_chart"]["headers"][0] == "EU"
    assert {c["name"] for c in p["colors"]} == {"Hitam", "Biru Navy", "Oranye"}
    assert len(p["variants"]) == 3 * 7
    assert client.get("/api/products/does-not-exist").status_code == 404


def test_size_based_pricing(client):
    p = client.get("/api/products/nordline-hydro-bottle").json()
    by_size = {v["size"]: v["price"] for v in p["variants"]}
    assert by_size["1 L"] - by_size["500 ml"] == 100_000


def test_full_checkout_flow(client):
    variant = first_in_stock(client, "velocita-aero-glide-3")
    stock_before = variant["stock"]

    cart = client.post("/api/carts").json()
    cart = client.post(f"/api/carts/{cart['id']}/items", json={"variant_id": variant["id"], "quantity": 2}).json()
    assert cart["item_count"] == 2
    assert cart["totals"]["subtotal"] == variant["price"] * 2

    cart = client.post(f"/api/carts/{cart['id']}/promo", json={"code": "stadion10"}).json()
    assert cart["totals"]["discount"] == min(variant["price"] * 2 // 10, 100_000)

    quoted = client.get(f"/api/carts/{cart['id']}", params={"shipping_method": "express"}).json()
    assert quoted["totals"]["shipping_fee"] == 35_000

    r = client.post("/api/checkout", json={
        "cart_id": cart["id"], "customer": CUSTOMER, "shipping_address": ADDRESS,
        "shipping_method": "express", "payment_method": "bank_transfer",
    })
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "pending_payment"
    assert order["total"] == quoted["totals"]["total"]
    assert order["payment_instructions"]

    # Stock decremented, cart consumed
    after = client.get(f"/api/variants/{variant['sku']}").json()
    assert after["stock"] == stock_before - 2
    assert client.get(f"/api/carts/{cart['id']}").status_code == 404

    # Ownership check by email
    assert client.get(f"/api/orders/{order['order_number']}", params={"email": "x@y.com"}).status_code == 404
    assert client.get(f"/api/orders/{order['order_number']}", params={"email": CUSTOMER["email"]}).status_code == 200

    paid = client.post(f"/api/orders/{order['order_number']}/pay").json()
    assert paid["status"] == "paid" and paid["paid_at"]
    assert client.post(f"/api/orders/{order['order_number']}/pay").status_code == 409

    cancelled = client.post(f"/api/orders/{order['order_number']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert client.get(f"/api/variants/{variant['sku']}").json()["stock"] == stock_before

    orders = client.get("/api/orders", params={"email": CUSTOMER["email"]}).json()
    assert any(o["order_number"] == order["order_number"] for o in orders)


def test_stock_and_validation_errors(client):
    variant = first_in_stock(client, "kinetik-drycore-tee")
    cart = client.post("/api/carts").json()

    too_many = client.post(f"/api/carts/{cart['id']}/items", json={"variant_id": variant["id"], "quantity": variant["stock"] + 1})
    assert too_many.status_code in (409, 422)

    assert client.post(f"/api/carts/{cart['id']}/promo", json={"code": "NOPE"}).status_code == 404

    empty = client.post("/api/checkout", json={
        "cart_id": cart["id"], "customer": CUSTOMER, "shipping_address": ADDRESS,
    })
    assert empty.status_code == 409

    client.post(f"/api/carts/{cart['id']}/items", json={"sku": variant["sku"], "quantity": 1})
    bad_postal = client.post("/api/checkout", json={
        "cart_id": cart["id"], "customer": CUSTOMER, "shipping_address": {**ADDRESS, "postal_code": "12"},
    })
    assert bad_postal.status_code == 422


def test_free_shipping_threshold(client):
    variant = first_in_stock(client, "velocita-carbon-elite")  # > Rp500.000
    cart = client.post("/api/carts").json()
    client.post(f"/api/carts/{cart['id']}/items", json={"variant_id": variant["id"], "quantity": 1})
    quoted = client.get(f"/api/carts/{cart['id']}", params={"shipping_method": "regular"}).json()
    assert quoted["totals"]["shipping_fee"] == 0


def test_info_handshake(client):
    info = client.get("/api/info").json()
    assert info["name"] == "Sport Stadion" and info["product_count"] == 29


def test_storefront_pages_served(client):
    for path in ["/", "/product/velocita-aero-glide-3", "/cart", "/checkout", "/order/SS-1", "/orders", "/static/app.js"]:
        assert client.get(path).status_code == 200, path


def test_web_sign_in_uses_the_chat_account_cart(client):
    email = "web-and-chat@example.com"
    headers = {"Accept": "application/json, text/event-stream", "X-Customer-Email": email}
    # A Conversify chat puts a cap in the account cart over MCP...
    client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "add_to_cart", "arguments": {"product": "kinetik-run-cap", "color": "Hitam", "size": "One Size"}}})

    # ...while the browser has an anonymous cart with a T-shirt.
    tee = first_in_stock(client, "kinetik-drycore-tee")
    anon = client.post("/api/carts").json()
    client.post(f"/api/carts/{anon['id']}/items", json={"variant_id": tee["id"], "quantity": 1})

    # Signing in (email is case-insensitive) returns the account cart with both items merged.
    cart = client.post("/api/carts/account", json={"email": "Web-And-Chat@example.com", "merge_cart_id": anon["id"]}).json()
    assert {i["product_slug"] for i in cart["items"]} == {"kinetik-run-cap", "kinetik-drycore-tee"}
    assert client.get(f"/api/carts/{anon['id']}").status_code == 404

    # The chat sees the merged cart too, and signing in again returns the same cart.
    view = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                                      "params": {"name": "view_cart", "arguments": {}}}).json()
    assert "Kinetik DryCore Tee" in view["result"]["content"][0]["text"]
    assert client.post("/api/carts/account", json={"email": email}).json()["id"] == cart["id"]
    assert client.post("/api/carts/account", json={"email": "not-an-email"}).status_code == 422

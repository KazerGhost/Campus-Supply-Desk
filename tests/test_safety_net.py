"""Safety-net tests for core OrderService domain rules."""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderSafetyNetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_valid_multi_item_order(self):
        items = [
            {"product_id": "hoodie", "quantity": 1},
            {"product_id": "mug", "quantity": 2},
        ]
        order = self.service.place_order("regular", items, "pickup")
        self.assertEqual(order["subtotal_cents"], 7000)
        self.assertEqual(order["discount_cents"], 0)
        self.assertEqual(order["delivery_cents"], 0)
        self.assertEqual(order["total_cents"], 7000)

        stock = {p["product_id"]: p["stock"] for p in self.service.catalog()}
        self.assertEqual(stock["hoodie"], 4)
        self.assertEqual(stock["mug"], 6)
        self.assertEqual(self.service.list_orders(), [order])

    def test_boundary_at_5000_cents(self):
        items = [{"product_id": "bag", "quantity": 2}]
        quote = self.service.quote("student", items, "pickup")
        order = self.service.place_order("student", items, "pickup")
        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)
        self.assertEqual(order["discount_cents"], 500)

    def test_boundary_at_10000_cents(self):
        items = [{"product_id": "bag", "quantity": 4}]
        quote = self.service.quote("regular", items, "delivery")
        order = self.service.place_order("regular", items, "delivery")
        self.assertEqual(quote["subtotal_cents"], 10000)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(order["total_cents"], 10000)

    def test_invalid_requests_do_not_change_stock_or_orders(self):
        initial_stock = self.service.catalog()
        with self.assertRaises(ValueError):
            self.service.quote("regular", [{"product_id": "notebook", "quantity": -1}])
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [{"product_id": "notebook", "quantity": 100}])
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [{"product_id": "bag", "quantity": 5}])
        with self.assertRaises(ValueError):
            self.service.get_order("ORD-9999")
        with self.assertRaises(ValueError):
            self.service.cancel_order("ORD-9999")

        self.assertEqual(self.service.catalog(), initial_stock)
        self.assertEqual(self.service.list_orders(), [])

    def test_quote_matches_place_order_without_saving_or_removing_stock(self):
        initial_stock = self.service.catalog()
        items = [
            {"product_id": "hoodie", "quantity": 1},
            {"product_id": "bag", "quantity": 1},
        ]
        quoted = self.service.quote("student", items, "delivery")
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.catalog(), initial_stock)

        placed = self.service.place_order("student", items, "delivery")
        for key in (
            "customer_type",
            "fulfillment",
            "items",
            "subtotal_cents",
            "discount_cents",
            "delivery_cents",
            "total_cents",
        ):
            self.assertEqual(quoted[key], placed[key])

    def test_cancel_order_is_idempotent(self):
        order = self.service.place_order("regular", [{"product_id": "hoodie", "quantity": 1}])
        self.assertEqual({p["product_id"]: p["stock"] for p in self.service.catalog()}["hoodie"], 4)

        self.service.cancel_order(order["order_id"])
        self.assertEqual({p["product_id"]: p["stock"] for p in self.service.catalog()}["hoodie"], 5)

        self.service.cancel_order(order["order_id"])
        self.assertEqual({p["product_id"]: p["stock"] for p in self.service.catalog()}["hoodie"], 5)

    def test_cr01_express_delivery_fee_applied_and_not_waived_over_threshold(self):
        items = [{"product_id": "hoodie", "quantity": 3}]
        
        quote_res = self.service.quote("regular", items, "express")
        self.assertEqual(quote_res["delivery_cents"], 1200)
        self.assertEqual(quote_res["total_cents"], 12000 + 1200)

    def test_cr01_express_student_discount_applies_only_to_merchandise(self):
        items = [{"product_id": "hoodie", "quantity": 2}]
        
        order = self.service.place_order("student", items, "express")
        self.assertEqual(order["subtotal_cents"], 8000)
        self.assertEqual(order["discount_cents"], 800)
        self.assertEqual(order["delivery_cents"], 1200)
        self.assertEqual(order["total_cents"], 8400)


if __name__ == "__main__":
    unittest.main()

import asyncio
import unittest
from auto_free_reward import FreeRewardManager, ClaimResult


class FreeRewardManagerTests(unittest.TestCase):
    def test_filter_free_products(self):
        manager = FreeRewardManager(api_request=lambda m, e, p=None: asyncio.sleep(0))
        products = [
            {"id": 1, "price": 100, "enabled": True, "productPaymentMethodId": 101},
            {"id": 653, "price": 0, "enabled": True, "productPaymentMethodId": 110599, "productCategoryId": 14, "actionId": "Webshop Free Reward 1"},
            {"id": 2, "price": 0, "enabled": False, "productPaymentMethodId": 102},  # disabled
            {"id": 3, "price": 0, "enabled": True, "productPaymentMethodId": None},  # no ppm
            {"id": 4, "price": 0, "enabled": True, "productPaymentMethodId": 104, "actionId": "Other Free Pack"},
        ]
        free = manager.filter_free_products(products)
        self.assertEqual(len(free), 2)
        # WebshopFree / category 14 has priority 0
        self.assertEqual(free[0]["id"], 653)
        self.assertEqual(free[1]["id"], 4)

    def test_claim_free_product_boss_coins(self):
        recorded_calls = []

        async def mock_api(method: str, endpoint: str, payload=None):
            recorded_calls.append((method, endpoint, payload))
            if endpoint == "/api/v1/bosscoinstorepurchase/process":
                return 200, [
                    {
                        "id": "bag-uuid-1",
                        "reward": {"id": 1402, "name": "Gold Bag", "type": 13, "value": 15},
                        "action": {"id": "Webshop Free Reward 1", "type": 15},
                    }
                ]
            elif endpoint == "/api/v1/user/randomrewards/bag-uuid-1/claim":
                return 200, [
                    [
                        {
                            "id": "reward-uuid-99",
                            "reward": {"id": 1049, "type": 1, "value": 50},
                            "action": {"id": "BossCoinConsumable_50", "type": 6},
                        }
                    ]
                ]
            elif endpoint == "/api/v1/user/bosscoinwallet/consumereward":
                return 200, {"amount": 300}
            return 404, {}

        manager = FreeRewardManager(api_request=mock_api)
        product = {
            "id": 653,
            "productPaymentMethodId": 110599,
            "actionId": "Webshop Free Reward 1",
            "title": "Free Reward",
        }
        result = asyncio.run(manager.claim_free_product(product))

        self.assertTrue(result.success)
        self.assertEqual(result.bag_name, "Gold Bag")
        self.assertEqual(result.coins_gained, 50)
        self.assertEqual(len(result.rewards), 1)
        self.assertEqual(result.rewards[0]["reward_id"], "reward-uuid-99")

        # Verify call sequence
        endpoints = [c[1] for c in recorded_calls]
        self.assertIn("/api/v1/bosscoinstorepurchase/process", endpoints)
        self.assertIn("/api/v1/user/randomrewards/bag-uuid-1/claim", endpoints)
        self.assertIn("/api/v1/user/bosscoinwallet/consumereward", endpoints)

    def test_claim_daily_login_bonus(self):
        recorded = []

        async def mock_api(method: str, endpoint: str, payload=None):
            recorded.append((method, endpoint))
            if endpoint == "/api/v1/user/bosscoinwallet" and method == "GET":
                return 200, {"unclaimedCoins": 4, "amount": 100}
            elif endpoint == "/api/v1/user/bosscoinwallet/claim" and method == "PUT":
                return 200, {"claimed": True}
            return 404, {}

        manager = FreeRewardManager(api_request=mock_api)
        coins = asyncio.run(manager.claim_daily_login_bonus())
        self.assertEqual(coins, 4)
        self.assertIn(("PUT", "/api/v1/user/bosscoinwallet/claim"), recorded)

    def test_reconcile_stops_when_purchase_rejected(self):
        attempts = 0

        async def mock_api(method: str, endpoint: str, payload=None):
            nonlocal attempts
            if endpoint == "/api/v1/user/bosscoinwallet":
                return 200, {"unclaimedCoins": 0}
            if endpoint == "/api/v1.1/products/web/":
                return 200, [
                    {"id": 653, "price": 0, "enabled": True, "productPaymentMethodId": 110599, "productCategoryId": 14}
                ]
            if endpoint == "/api/v1/bosscoinstorepurchase/process":
                attempts += 1
                if attempts == 1:
                    return 200, [
                        {
                            "id": "bag-1",
                            "reward": {"id": 1402, "name": "Gold Bag", "type": 13, "value": 15},
                            "action": {"type": 15},
                        }
                    ]
                else:
                    # Limit reached on second attempt
                    return 400, {"error": "Limit reached"}
            if endpoint == "/api/v1/user/randomrewards/bag-1/claim":
                return 200, [[{"id": "r-1", "reward": {"type": 1, "value": 10}}]]
            if endpoint == "/api/v1/user/bosscoinwallet/consumereward":
                return 200, {}
            return 404, {}

        manager = FreeRewardManager(api_request=mock_api)
        results = asyncio.run(manager.reconcile(check_actions=False))
        self.assertEqual(len(results), 1)
        self.assertEqual(attempts, 2)
        self.assertEqual(results[0].coins_gained, 10)

    def test_claim_action_reward(self):
        recorded = []

        async def mock_api(method: str, endpoint: str, payload=None):
            recorded.append((method, endpoint))
            if endpoint.startswith("/api/v1/user/actions/"):
                return 200, [
                    {
                        "id": "action-reward-1",
                        "reward": {"id": 1001, "type": 1, "value": 25},
                    }
                ]
            elif endpoint == "/api/v1/user/bosscoinwallet/consumereward":
                return 200, {}
            return 404, {}

        manager = FreeRewardManager(api_request=mock_api)
        result = asyncio.run(manager.claim_action_reward("Webshop Free Reward 1"))
        self.assertTrue(result.success)
        self.assertEqual(result.coins_gained, 25)
        self.assertEqual(manager.stats["coins_gained"], 25)

    def test_run_parallel_workers(self):
        claim_counter = 0

        async def mock_api(method: str, endpoint: str, payload=None):
            nonlocal claim_counter
            if endpoint == "/api/v1/user/bosscoinwallet":
                return 200, {"unclaimedCoins": 0}
            if endpoint == "/api/v1.1/products/web/":
                return 200, [
                    {"id": 653, "price": 0, "enabled": True, "productPaymentMethodId": 110599, "productCategoryId": 14}
                ]
            if endpoint == "/api/v1/bosscoinstorepurchase/process":
                claim_counter += 1
                return 200, [
                    {
                        "id": f"bag-{claim_counter}",
                        "reward": {"type": 1, "value": 5},
                    }
                ]
            if endpoint == "/api/v1/user/bosscoinwallet/consumereward":
                return 200, {}
            return 404, {}

        manager = FreeRewardManager(api_request=mock_api, log=lambda _: None)
        # Test running 3 parallel workers until max_claims=6 is reached
        asyncio.run(
            manager.run_parallel(
                workers=3,
                delay=0.01,
                max_claims=6,
                check_actions=False,
            )
        )
        self.assertGreaterEqual(manager.stats["claims_count"], 6)
        self.assertGreaterEqual(manager.stats["coins_gained"], 30)


if __name__ == "__main__":
    unittest.main()

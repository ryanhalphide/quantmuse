// Plain-assert smoke/regression test for the classes exposed to Python via
// bindings.cpp (order lifecycle, portfolio valuation, risk gating, threaded
// order execution, strategy signal generation). Exercised directly in C++
// so it runs under ctest without needing Python or the compiled extension.
//
// No gtest dependency (the pre-existing test_risk_manager.cpp/
// test_data_loader.cpp use gtest but were never wired into CMakeLists.txt --
// out of scope here) -- plain asserts registered via add_test() instead.

#include "common/types.hpp"
#include "order_executor.hpp"
#include "risk_manager.hpp"
#include "strategy.hpp"

#include <cassert>
#include <chrono>
#include <cstdio>
#include <thread>

using namespace trading;

static void test_order_lifecycle() {
    Order order("AAPL", OrderSide::BUY, OrderType::MARKET, 10.0);
    assert(order.getSymbol() == "AAPL");
    assert(order.getStatus() == OrderStatus::PENDING);
    order.setPrice(150.0);
    assert(order.getPrice() == 150.0);
    printf("test_order_lifecycle passed\n");
}

static void test_portfolio_valuation() {
    Portfolio portfolio;
    portfolio.updatePosition("AAPL", 10, 150.0);
    std::map<std::string, double> prices{{"AAPL", 155.0}};
    double expected = portfolio.getCash() + 10 * 155.0;
    assert(portfolio.getTotalValue(prices) == expected);
    printf("test_portfolio_valuation passed\n");
}

static void test_risk_manager_gates_oversized_order() {
    RiskManager::RiskLimits limits{0.1, 0.2, 2.0, 10000.0, 0.3};
    RiskManager rm(limits);
    Portfolio portfolio;  // cash_ defaults to 1,000,000
    rm.updateCurrentPrices({{"AAPL", 100.0}});

    Order small_order("AAPL", OrderSide::BUY, OrderType::MARKET, 1.0);
    small_order.setPrice(100.0);  // position_value = 100, well under 10% of 1M
    assert(rm.checkOrderRisk(small_order, portfolio) == true);

    Order huge_order("AAPL", OrderSide::BUY, OrderType::MARKET, 5000.0);
    huge_order.setPrice(100.0);  // position_value = 500,000 > 10% of 1M
    assert(rm.checkOrderRisk(huge_order, portfolio) == false);
    printf("test_risk_manager_gates_oversized_order passed\n");
}

static void test_risk_manager_sell_concentration_is_signed() {
    // Regression test: a SELL must reduce the resulting position for the
    // concentration check, not add to it -- otherwise every sell of an
    // existing position looks like it doubles exposure and gets rejected.
    RiskManager::RiskLimits limits{0.9, 0.9, 5.0, 1e9, 0.015};
    RiskManager rm(limits);
    Portfolio portfolio;
    portfolio.updatePosition("AAPL", 100.0, 100.0);  // existing 100-share position
    rm.updateCurrentPrices({{"AAPL", 100.0}});
    // portfolio_value = 1,000,000 cash + 100*100 position = 1,010,000
    // Old (buggy) concentration: (100 existing + 100 sold)*100 / 1,010,000 = 0.0198 > 0.015 -> rejected
    // Fixed concentration: |100 existing - 100 sold| * 100 / 1,010,000 = 0 -> accepted

    Order sell_order("AAPL", OrderSide::SELL, OrderType::MARKET, 100.0);
    sell_order.setPrice(100.0);
    assert(rm.checkOrderRisk(sell_order, portfolio) == true);
    printf("test_risk_manager_sell_concentration_is_signed passed\n");
}

static void test_order_executor_fills_orders() {
    OrderExecutor executor;
    executor.start();

    auto order = std::make_shared<Order>("AAPL", OrderSide::BUY, OrderType::MARKET, 10.0);
    executor.submitOrder(order);

    // Bounded poll -- executeOrder fills near-instantly on its own thread.
    for (int i = 0; i < 1000 &&
         executor.getOrderStatus(order->getOrderId()) == OrderStatus::PENDING; ++i) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    assert(executor.getOrderStatus(order->getOrderId()) == OrderStatus::FILLED);
    executor.stop();
    printf("test_order_executor_fills_orders passed\n");
}

static void test_order_executor_cancel() {
    OrderExecutor executor;  // not started -- order stays queued/PENDING
    auto order = std::make_shared<Order>("AAPL", OrderSide::SELL, OrderType::MARKET, 5.0);
    executor.submitOrder(order);
    executor.cancelOrder(order->getOrderId());
    assert(executor.getOrderStatus(order->getOrderId()) == OrderStatus::CANCELLED);
    printf("test_order_executor_cancel passed\n");
}

static void test_moving_average_strategy() {
    MovingAverageStrategy strategy(2, 4);
    strategy.initialize();

    MarketData md;
    md.symbol = "AAPL";
    std::vector<double> prices = {100, 101, 102, 103, 110};
    std::vector<Strategy::Signal> last_signals;
    for (double p : prices) {
        md.last_price = p;
        last_signals = strategy.onMarketData(md);
    }
    assert(!last_signals.empty());
    printf("test_moving_average_strategy passed\n");
}

int main() {
    test_order_lifecycle();
    test_portfolio_valuation();
    test_risk_manager_gates_oversized_order();
    test_risk_manager_sell_concentration_is_signed();
    test_order_executor_fills_orders();
    test_order_executor_cancel();
    test_moving_average_strategy();
    printf("ALL BINDING TESTS PASSED\n");
    return 0;
}

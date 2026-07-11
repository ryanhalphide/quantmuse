// Python bindings for the QuantMuse C++ trading engine.
// Exposes MarketData/Order/Position/Portfolio, RiskManager, OrderExecutor,
// and the Strategy hierarchy (with a trampoline so Python code can subclass
// Strategy) as the `quantmuse_engine` extension module.
//
// This is intentionally independent of data_loader.hpp/main.cpp -- those
// embed a Python interpreter *inside* C++ (the reverse integration
// direction) and depend on components (Config, Logger) that don't exist in
// this repo yet. This module instead exposes C++ *to* Python, so it only
// needs common/types.hpp, order_executor, risk_manager, and strategy.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

#include "common/types.hpp"
#include "order_executor.hpp"
#include "risk_manager.hpp"
#include "strategy.hpp"

namespace py = pybind11;
using namespace trading;

namespace {

// Trampoline so Python subclasses can override Strategy's pure virtuals.
class PyStrategy : public Strategy {
public:
    using Strategy::Strategy;

    void initialize() override {
        PYBIND11_OVERRIDE_PURE(void, Strategy, initialize);
    }
    std::vector<Signal> onMarketData(const MarketData& data) override {
        PYBIND11_OVERRIDE_PURE(std::vector<Signal>, Strategy, onMarketData, data);
    }
    void onOrderUpdate(const Order& order) override {
        PYBIND11_OVERRIDE_PURE(void, Strategy, onOrderUpdate, order);
    }
};

} // namespace

PYBIND11_MODULE(quantmuse_engine, m) {
    m.doc() = "QuantMuse C++ trading engine bindings (order execution, risk, strategy)";

    // --- Order enums ---------------------------------------------------
    py::enum_<OrderSide>(m, "OrderSide")
        .value("BUY", OrderSide::BUY)
        .value("SELL", OrderSide::SELL);

    py::enum_<OrderType>(m, "OrderType")
        .value("MARKET", OrderType::MARKET)
        .value("LIMIT", OrderType::LIMIT)
        .value("STOP", OrderType::STOP)
        .value("STOP_LIMIT", OrderType::STOP_LIMIT);

    py::enum_<OrderStatus>(m, "OrderStatus")
        .value("PENDING", OrderStatus::PENDING)
        .value("FILLED", OrderStatus::FILLED)
        .value("PARTIALLY_FILLED", OrderStatus::PARTIALLY_FILLED)
        .value("CANCELLED", OrderStatus::CANCELLED)
        .value("REJECTED", OrderStatus::REJECTED);

    // --- MarketData ------------------------------------------------------
    py::class_<MarketData>(m, "MarketData")
        .def(py::init<>())
        .def_readwrite("symbol", &MarketData::symbol)
        .def_readwrite("last_price", &MarketData::last_price)
        .def_readwrite("open", &MarketData::open)
        .def_readwrite("high", &MarketData::high)
        .def_readwrite("low", &MarketData::low)
        .def_readwrite("volume", &MarketData::volume)
        .def_readwrite("timestamp", &MarketData::timestamp)
        .def_readwrite("indicators", &MarketData::indicators)
        .def_readwrite("fundamentals", &MarketData::fundamentals);

    // --- Order -----------------------------------------------------------
    py::class_<Order, std::shared_ptr<Order>>(m, "Order")
        .def(py::init<const std::string&, OrderSide, OrderType, double>(),
             py::arg("symbol"), py::arg("side"), py::arg("type"), py::arg("quantity"))
        .def("get_order_id", &Order::getOrderId)
        .def("get_symbol", &Order::getSymbol)
        .def("get_side", &Order::getSide)
        .def("get_type", &Order::getType)
        .def("get_quantity", &Order::getQuantity)
        .def("get_price", &Order::getPrice)
        .def("get_status", &Order::getStatus)
        .def("set_price", &Order::setPrice)
        .def("set_status", &Order::setStatus)
        .def("set_filled_quantity", &Order::setFilledQuantity);

    // --- Position / Portfolio ---------------------------------------------
    py::class_<Position, std::shared_ptr<Position>>(m, "Position")
        .def(py::init<const std::string&>())
        .def("update_position", &Position::updatePosition)
        .def("get_quantity", &Position::getQuantity)
        .def("get_average_price", &Position::getAveragePrice)
        .def("get_market_value", &Position::getMarketValue)
        .def("get_unrealized_pnl", &Position::getUnrealizedPnL);

    py::class_<Portfolio>(m, "Portfolio")
        .def(py::init<>())
        .def("update_position", &Portfolio::updatePosition)
        .def("get_total_value", &Portfolio::getTotalValue)
        .def("get_cash", &Portfolio::getCash)
        .def("update_cash", &Portfolio::updateCash)
        .def("get_position", &Portfolio::getPosition)
        .def("get_total_exposure", &Portfolio::getTotalExposure)
        .def("get_drawdown", &Portfolio::getDrawdown)
        .def("get_leverage", &Portfolio::getLeverage)
        .def("get_daily_pnl", &Portfolio::getDailyPnL)
        .def("get_concentration", &Portfolio::getConcentration);

    // --- RiskManager -------------------------------------------------------
    py::class_<RiskManager::RiskLimits>(m, "RiskLimits")
        .def(py::init<>())
        .def_readwrite("max_position_size", &RiskManager::RiskLimits::max_position_size)
        .def_readwrite("max_drawdown", &RiskManager::RiskLimits::max_drawdown)
        .def_readwrite("max_leverage", &RiskManager::RiskLimits::max_leverage)
        .def_readwrite("daily_loss_limit", &RiskManager::RiskLimits::daily_loss_limit)
        .def_readwrite("position_concentration", &RiskManager::RiskLimits::position_concentration);

    py::class_<RiskManager>(m, "RiskManager")
        .def(py::init<const RiskManager::RiskLimits&>())
        .def("check_order_risk", &RiskManager::checkOrderRisk)
        .def("update_risk_metrics", &RiskManager::updateRiskMetrics)
        .def("get_risk_metrics", &RiskManager::getRiskMetrics)
        .def("update_current_prices", &RiskManager::updateCurrentPrices);

    // --- OrderExecutor -------------------------------------------------------
    py::class_<OrderExecutor>(m, "OrderExecutor")
        .def(py::init<>())
        .def("start", &OrderExecutor::start, py::call_guard<py::gil_scoped_release>())
        .def("stop", &OrderExecutor::stop, py::call_guard<py::gil_scoped_release>())
        .def("submit_order", &OrderExecutor::submitOrder)
        .def("cancel_order", &OrderExecutor::cancelOrder)
        .def("get_order_status", &OrderExecutor::getOrderStatus);

    // --- Strategy (abstract; trampoline lets Python subclass it) -----------
    py::class_<Strategy::Signal>(m, "Signal")
        .def(py::init<>())
        .def_readwrite("symbol", &Strategy::Signal::symbol)
        .def_readwrite("side", &Strategy::Signal::side)
        .def_readwrite("strength", &Strategy::Signal::strength)
        .def_readwrite("timestamp", &Strategy::Signal::timestamp);

    py::class_<Strategy, PyStrategy, std::shared_ptr<Strategy>>(m, "Strategy")
        .def(py::init<>())
        .def("initialize", &Strategy::initialize)
        .def("on_market_data", &Strategy::onMarketData)
        .def("on_order_update", &Strategy::onOrderUpdate);

    py::class_<MovingAverageStrategy, Strategy, std::shared_ptr<MovingAverageStrategy>>(
        m, "MovingAverageStrategy")
        .def(py::init<int, int>(), py::arg("short_period") = 10, py::arg("long_period") = 30)
        .def("initialize", &MovingAverageStrategy::initialize)
        .def("on_market_data", &MovingAverageStrategy::onMarketData)
        .def("on_order_update", &MovingAverageStrategy::onOrderUpdate);
}

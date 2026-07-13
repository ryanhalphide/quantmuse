#include "risk_manager.hpp"
#include <spdlog/spdlog.h>
#include <algorithm>
#include <cmath>

namespace trading {

RiskManager::RiskManager(const RiskLimits& limits) : limits_(limits) {}

bool RiskManager::checkOrderRisk(const Order& order, const Portfolio& portfolio) {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    
    try {
        // 1. 检查单个持仓限制
        double position_value = order.getQuantity() * order.getPrice();
        double portfolio_value = portfolio.getTotalValue(current_prices_);
        
        if (position_value / portfolio_value > limits_.max_position_size) {
            spdlog::warn("Position size limit exceeded for {}", order.getSymbol());
            return false;
        }
        
        // 2. 检查杠杆限制
        double total_exposure = portfolio.getTotalExposure() + position_value;
        if (total_exposure / portfolio_value > limits_.max_leverage) {
            spdlog::warn("Leverage limit exceeded");
            return false;
        }
        
        // 3. 检查回撤限制
        if (portfolio.getDrawdown() > limits_.max_drawdown) {
            spdlog::warn("Drawdown limit exceeded");
            return false;
        }
        
        // 4. 检查每日损失限制
        if (portfolio.getDailyPnL() < -limits_.daily_loss_limit) {
            spdlog::warn("Daily loss limit exceeded");
            return false;
        }
        
        // 5. 检查集中度限制
        // A SELL reduces (or reverses) the existing position rather than
        // adding to it -- use a signed delta so a sell order's concentration
        // is evaluated against the resulting position, not the existing one
        // plus the sell quantity (which would make every sell look like it
        // doubles exposure).
        auto position = portfolio.getPosition(order.getSymbol());
        double existing_quantity = position ? position->getQuantity() : 0;
        double signed_delta = (order.getSide() == OrderSide::BUY)
            ? order.getQuantity() : -order.getQuantity();
        double new_position_size = existing_quantity + signed_delta;
        double new_concentration = std::abs(new_position_size) * order.getPrice() / portfolio_value;
        
        if (new_concentration > limits_.position_concentration) {
            spdlog::warn("Position concentration limit exceeded for {}", order.getSymbol());
            return false;
        }
        
        // 更新风险指标
        updateRiskMetrics(portfolio);
        return true;
        
    } catch (const std::exception& e) {
        spdlog::error("Error in risk check: {}", e.what());
        return false;
    }
}

void RiskManager::updateRiskMetrics(const Portfolio& portfolio) {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    
    try {
        // 更新风险指标
        current_metrics_["drawdown"] = portfolio.getDrawdown();
        current_metrics_["leverage"] = portfolio.getLeverage();
        current_metrics_["daily_pnl"] = portfolio.getDailyPnL();
        current_metrics_["concentration"] = portfolio.getConcentration();
        
        // 记录风险指标
        spdlog::debug("Risk metrics updated: drawdown={:.2f}%, leverage={:.2f}x, daily_pnl=${:.2f}",
            current_metrics_["drawdown"] * 100,
            current_metrics_["leverage"],
            current_metrics_["daily_pnl"]);
            
    } catch (const std::exception& e) {
        spdlog::error("Error updating risk metrics: {}", e.what());
    }
}

std::map<std::string, double> RiskManager::getRiskMetrics() const {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    return current_metrics_;
}

void RiskManager::updateCurrentPrices(const std::map<std::string, double>& prices) {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    current_prices_ = prices;
}

} // namespace trading 
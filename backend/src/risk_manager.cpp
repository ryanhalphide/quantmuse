#include "risk_manager.hpp"
#include <spdlog/spdlog.h>
#include <algorithm>
#include <cmath>

namespace trading {

RiskManager::RiskManager(const RiskLimits& limits) : limits_(limits) {}

bool RiskManager::checkOrderRisk(const Order& order, const Portfolio& portfolio) {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    
    try {
        double portfolio_value = portfolio.getTotalValue(current_prices_);
        if (!std::isfinite(portfolio_value) || portfolio_value <= 0.0) {
            last_rejection_reason_ = "no_portfolio_value";
            spdlog::warn("Cannot risk-check {}: portfolio value is {}", order.getSymbol(), portfolio_value);
            return false;
        }

        // 1. 检查单个持仓限制
        double position_value = order.getQuantity() * order.getPrice();
        if (position_value / portfolio_value > limits_.max_position_size) {
            last_rejection_reason_ = "position_size_limit";
            spdlog::warn("Position size limit exceeded for {}", order.getSymbol());
            return false;
        }

        // Signed post-trade position for this symbol -- a SELL reduces (or
        // reverses) the existing position rather than adding to it. Reused
        // by both the leverage and concentration checks below so a SELL
        // that reduces/closes exposure isn't treated as increasing it.
        auto position = portfolio.getPosition(order.getSymbol());
        double existing_quantity = position ? position->getQuantity() : 0;
        double signed_delta = (order.getSide() == OrderSide::BUY)
            ? order.getQuantity() : -order.getQuantity();
        double new_position_size = existing_quantity + signed_delta;

        // 2. 检查杠杆限制
        // Replace this symbol's contribution to gross exposure with its
        // post-trade value, rather than unconditionally adding the order's
        // notional -- the latter made every SELL (even one that reduces or
        // closes a position) look like it increases leverage. The existing
        // contribution is valued at the same current_prices_ mark used to
        // compute portfolio.getTotalExposure() in the first place; the
        // post-trade contribution is valued at the order's own price, like
        // the position-size check above.
        auto mark_it = current_prices_.find(order.getSymbol());
        double mark_price = (mark_it != current_prices_.end()) ? mark_it->second : order.getPrice();
        double existing_symbol_exposure = std::abs(existing_quantity) * mark_price;
        double new_symbol_exposure = std::abs(new_position_size) * order.getPrice();
        double total_exposure = portfolio.getTotalExposure() - existing_symbol_exposure + new_symbol_exposure;
        if (total_exposure / portfolio_value > limits_.max_leverage) {
            last_rejection_reason_ = "leverage_limit";
            spdlog::warn("Leverage limit exceeded");
            return false;
        }

        // 3. 检查回撤限制
        if (portfolio.getDrawdown() > limits_.max_drawdown) {
            last_rejection_reason_ = "drawdown_limit";
            spdlog::warn("Drawdown limit exceeded");
            return false;
        }

        // 4. 检查每日损失限制
        if (portfolio.getDailyPnL() < -limits_.daily_loss_limit) {
            last_rejection_reason_ = "daily_loss_limit";
            spdlog::warn("Daily loss limit exceeded");
            return false;
        }

        // 5. 检查集中度限制
        double new_concentration = new_symbol_exposure / portfolio_value;
        if (new_concentration > limits_.position_concentration) {
            last_rejection_reason_ = "concentration_limit";
            spdlog::warn("Position concentration limit exceeded for {}", order.getSymbol());
            return false;
        }

        last_rejection_reason_.clear();
        // 更新风险指标
        updateRiskMetrics(portfolio);
        return true;

    } catch (const std::exception& e) {
        last_rejection_reason_ = "internal_error";
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

std::string RiskManager::getLastRejectionReason() const {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    return last_rejection_reason_;
}

} // namespace trading 
#pragma once
#include "common/types.hpp"
#include <memory>
#include <map>
#include <mutex>

namespace trading {

class RiskManager {
public:
    struct RiskLimits {
        double max_position_size;
        double max_drawdown;
        double max_leverage;
        double daily_loss_limit;
        double position_concentration;
    };

    RiskManager(const RiskLimits& limits);
    bool checkOrderRisk(const Order& order, const Portfolio& portfolio);
    void updateRiskMetrics(const Portfolio& portfolio);
    std::map<std::string, double> getRiskMetrics() const;
    void updateCurrentPrices(const std::map<std::string, double>& prices);
    // Empty string if the last checkOrderRisk() call passed; otherwise one of
    // "position_size_limit"/"leverage_limit"/"drawdown_limit"/
    // "daily_loss_limit"/"concentration_limit"/"no_portfolio_value". Purely
    // additive -- checkOrderRisk()'s bool return value and existing callers
    // are unaffected whether or not this is read.
    std::string getLastRejectionReason() const;

private:
    RiskLimits limits_;
    std::map<std::string, double> current_metrics_;
    std::map<std::string, double> current_prices_;
    std::string last_rejection_reason_;
    // Recursive: checkOrderRisk() calls updateRiskMetrics() while holding
    // this lock, so a plain std::mutex would self-deadlock on relock.
    mutable std::recursive_mutex mutex_;
};

} // namespace trading

#pragma once
#include <string>
#include <memory>
#include <vector>
#include <functional>
#include "common/types.hpp"

namespace trading {

class DataLoader {
public:
    DataLoader();
    ~DataLoader();

    // 从Python数据服务获取数据
    MarketData loadMarketData(const std::string& symbol);
    
    // 获取历史数据
    std::vector<MarketData> loadHistoricalData(
        const std::string& symbol,
        const Timestamp& start,
        const Timestamp& end
    );
    
    // 订阅实时数据
    void subscribeToRealTimeData(
        const std::string& symbol,
        std::function<void(const MarketData&)> callback
    );

private:
    // Pimpl hides the pybind11/Python-embedding details (py::module, py::object)
    // from this header, so consumers of DataLoader don't need Python.h in scope.
    class Impl;
    std::unique_ptr<Impl> pimpl_;
};

} // namespace trading

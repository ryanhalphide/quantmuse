#pragma once
#include "common/types.hpp"
#include <queue>
#include <thread>
#include <atomic>
#include <condition_variable>
#include <map>
#include <stdexcept>

namespace trading {

class OrderExecutor {
public:
    OrderExecutor();
    ~OrderExecutor();

    void start();
    void stop();
    void submitOrder(std::shared_ptr<Order> order);
    void cancelOrder(const std::string& order_id);
    OrderStatus getOrderStatus(const std::string& order_id);

private:
    void executionLoop();
    void executeOrder(std::shared_ptr<Order> order);

    std::queue<std::shared_ptr<Order>> order_queue_;
    // Tracks every submitted order by id so status can be queried/cancelled
    // after it leaves order_queue_ (the queue alone doesn't support lookup).
    std::map<std::string, std::shared_ptr<Order>> orders_;
    std::atomic<bool> running_;
    std::thread execution_thread_;
    std::mutex mutex_;
    std::condition_variable cv_;
};

} // namespace trading

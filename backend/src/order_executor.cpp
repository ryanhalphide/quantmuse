#include "order_executor.hpp"
#include <spdlog/spdlog.h>

namespace trading {

OrderExecutor::OrderExecutor() : running_(false) {
}

OrderExecutor::~OrderExecutor() {
    stop();
}

void OrderExecutor::start() {
    running_ = true;
    execution_thread_ = std::thread(&OrderExecutor::executionLoop, this);
    spdlog::info("Order executor started");
}

void OrderExecutor::stop() {
    running_ = false;
    cv_.notify_one();
    
    if (execution_thread_.joinable()) {
        execution_thread_.join();
    }
    spdlog::info("Order executor stopped");
}

void OrderExecutor::submitOrder(std::shared_ptr<Order> order) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        order_queue_.push(order);
        orders_[order->getOrderId()] = order;
    }
    cv_.notify_one();
    spdlog::info("Order submitted: {}", order->getOrderId());
}

void OrderExecutor::cancelOrder(const std::string& order_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = orders_.find(order_id);
    if (it == orders_.end()) {
        throw std::runtime_error("Unknown order id: " + order_id);
    }
    // The order may already have left order_queue_ for execution; executeOrder
    // checks for this status and skips filling a cancelled order.
    if (it->second->getStatus() == OrderStatus::PENDING) {
        it->second->setStatus(OrderStatus::CANCELLED);
        spdlog::info("Order cancelled: {}", order_id);
    }
}

OrderStatus OrderExecutor::getOrderStatus(const std::string& order_id) {
    std::lock_guard<std::mutex> lock(mutex_);
    auto it = orders_.find(order_id);
    if (it == orders_.end()) {
        throw std::runtime_error("Unknown order id: " + order_id);
    }
    return it->second->getStatus();
}

void OrderExecutor::executionLoop() {
    while (running_) {
        std::shared_ptr<Order> order;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            cv_.wait(lock, [this] { 
                return !order_queue_.empty() || !running_; 
            });
            
            if (!running_) break;
            
            order = order_queue_.front();
            order_queue_.pop();
        }
        
        executeOrder(order);
    }
}

void OrderExecutor::executeOrder(std::shared_ptr<Order> order) {
    if (order->getStatus() == OrderStatus::CANCELLED) {
        spdlog::info("Skipping cancelled order: {}", order->getOrderId());
        return;
    }
    try {
        // 实现实际的订单执行逻辑
        order->setStatus(OrderStatus::FILLED);
        spdlog::info("Order executed: {}", order->getOrderId());
        
    } catch (const std::exception& e) {
        order->setStatus(OrderStatus::REJECTED);
        spdlog::error("Order execution failed: {}", e.what());
    }
}

} // namespace trading

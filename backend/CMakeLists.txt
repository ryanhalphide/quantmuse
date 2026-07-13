cmake_minimum_required(VERSION 3.12)
project(trading_engine)

# 设置C++标准
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找依赖包
find_package(pybind11 REQUIRED)  # Python接口
find_package(spdlog REQUIRED)    # 日志
find_package(nlohmann_json REQUIRED)  # JSON处理
find_package(Boost REQUIRED COMPONENTS system)  # Boost

# 添加头文件路径
include_directories(${CMAKE_SOURCE_DIR}/include)

# 收集源文件 (excludes bindings.cpp -- that's a pybind11 module entry point,
# not part of the standalone trading_engine executable; see below)
file(GLOB_RECURSE SOURCES "src/*.cpp")
list(REMOVE_ITEM SOURCES "${CMAKE_SOURCE_DIR}/src/bindings.cpp")

# 创建可执行文件
add_executable(trading_engine ${SOURCES})

# 链接依赖库
target_link_libraries(trading_engine
    PRIVATE
        pybind11::embed
        spdlog::spdlog
        nlohmann_json::nlohmann_json
        Boost::system
        pthread
)

# Python extension module exposing MarketData/Order/Position/Portfolio,
# RiskManager, OrderExecutor, and Strategy to Python. This is the opposite
# integration direction from data_loader.cpp (which embeds Python inside
# C++), so it only needs types.hpp (header-only), order_executor.cpp,
# risk_manager.cpp, and strategy.cpp -- not data_loader.cpp or main.cpp.
#
# Build with: cmake -B build -DBUILD_PYTHON_MODULE=ON && cmake --build build
option(BUILD_PYTHON_MODULE "Build the quantmuse_engine Python extension module" OFF)
if(BUILD_PYTHON_MODULE)
    pybind11_add_module(quantmuse_engine
        src/bindings.cpp
        src/order_executor.cpp
        src/risk_manager.cpp
        src/strategy.cpp
    )
    target_link_libraries(quantmuse_engine PRIVATE spdlog::spdlog)
endif()

# C++-side smoke/regression test for the classes bindings.cpp exposes to
# Python. Pure C++, no pybind11/Python needed, so it builds unconditionally.
enable_testing()
add_executable(test_bindings
    tests/test_bindings.cpp
    src/order_executor.cpp
    src/risk_manager.cpp
    src/strategy.cpp
)
target_link_libraries(test_bindings PRIVATE spdlog::spdlog pthread)
add_test(NAME test_bindings COMMAND test_bindings)

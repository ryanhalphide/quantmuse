# 量化交易策略集合

基于我们的量化因子分析框架，这里提供了多个实用的量化交易策略，涵盖不同的投资风格和风险偏好。

> **API 说明 / API note**: 策略框架是基于类的 (`StrategyBase` 的子类)，通过
> `StrategyRunner` 运行。下面代码示例中的 `strategies.xxx_strategy(...)` 函数式调用
> 并不存在 — 请使用下面的真实接口。当前内置 5 个策略并已注册：
> `MomentumStrategy`、`ValueStrategy`、`QualityGrowthStrategy`、
> `MultiFactorStrategy`、`MeanReversionStrategy`。其余策略 (低波动、行业轮动、
> 风险平价) 为设计概念，尚未内置 — 可通过继承 `StrategyBase` 自行实现。
> 完整可运行指南见 [`USAGE.md`](USAGE.md) §7。
>
> ```python
> from data_service.strategies import StrategyRunner
> from data_service.strategies.builtin_strategies import register_builtin_strategies
>
> register_builtin_strategies()          # 注册 5 个内置策略
> runner = StrategyRunner()
> # factor_data / price_data 为横截面 DataFrame (行 = 股票代码)
> result = runner.run_strategy("MomentumStrategy", factor_data, price_data,
>                              parameters={"top_n": 20, "min_momentum": 5.0})
> print(result.selected_stocks, result.weights, result.performance_metrics)
> ```

## 🎯 策略概览

| 策略名称 | 投资风格 | 风险等级 | 适用市场 | 换手率 |
|---------|---------|---------|---------|--------|
| 动量策略 | 趋势跟踪 | 中高 | 牛市 | 高 |
| 价值策略 | 价值投资 | 中 | 震荡市 | 低 |
| 质量成长策略 | 成长投资 | 中高 | 成长股 | 中 |
| 多因子策略 | 综合 | 中 | 全市场 | 中 |
| 均值回归策略 | 反转 | 中高 | 震荡市 | 高 |
| 低波动策略 | 防御 | 低 | 熊市 | 低 |
| 行业轮动策略 | 宏观 | 中高 | 周期股 | 高 |
| 风险平价策略 | 风险控制 | 中 | 全市场 | 中 |

## 📊 详细策略说明

### 1. 动量策略 (Momentum Strategy)

**核心理念**: 趋势会延续，强者恒强

**策略逻辑**:
- 选择过去60天动量最强的股票
- 等权重配置
- 月度调仓

**适用条件**:
- 市场处于上升趋势
- 流动性充足
- 波动率适中

**风险提示**:
- 趋势反转时损失较大
- 需要及时止损
- 换手率较高

```python
# 动量策略示例
momentum_result = runner.run_strategy(
    "MomentumStrategy", factor_data, price_data,
    parameters={"lookback_period": 60,  # 60天动量
                "top_n": 20,            # 选择前20只股票
                "min_momentum": 5.0}
)
```

### 2. 价值策略 (Value Strategy)

**核心理念**: 价格终将回归价值

**策略逻辑**:
- 选择低P/E、低P/B的股票
- 要求股息率>2%
- ROE>10%
- 季度调仓

**适用条件**:
- 市场估值合理或偏低
- 经济基本面稳定
- 利率环境适中

**风险提示**:
- 价值陷阱风险
- 需要耐心等待
- 可能错过成长股

```python
# 价值策略示例
value_result = runner.run_strategy(
    "ValueStrategy", factor_data, price_data,
    parameters={"max_pe": 15.0,             # P/E < 15
                "max_pb": 2.0,              # P/B < 2
                "min_dividend_yield": 2.0,  # 股息率 > 2%
                "top_n": 30}               # 选择30只股票
)
```

### 3. 质量成长策略 (Quality Growth Strategy)

**核心理念**: 优质公司长期创造价值

**策略逻辑**:
- ROE > 15%
- 负债率 < 50%
- 流动比率 > 1.5
- 60天动量 > 10%

**适用条件**:
- 经济稳定增长
- 行业集中度提升
- 利率环境宽松

**风险提示**:
- 估值可能过高
- 对经济周期敏感
- 需要深度研究

```python
# 质量成长策略示例
quality_result = runner.run_strategy(
    "QualityGrowthStrategy", factor_data, price_data,
    parameters={"min_roe": 15.0,       # ROE > 15%
                "min_growth": 10.0,    # 动量 > 10%
                "max_debt_equity": 0.5,
                "min_current_ratio": 1.5}
)
```

### 4. 多因子策略 (Multi-Factor Strategy)

**核心理念**: 多维度评估，分散风险

**策略逻辑**:
- 动量因子 30%
- 价值因子 20%
- 质量因子 20%
- 波动率因子 15%
- 规模因子 15%

**适用条件**:
- 全市场环境
- 因子有效性稳定
- 数据质量良好

**风险提示**:
- 因子失效风险
- 需要持续优化
- 计算复杂度高

```python
# 多因子策略示例
factor_weights = {
    'momentum_60d': 0.3,
    'pe_ratio': 0.2,
    'roe': 0.2,
    'price_volatility': 0.15,
    'market_cap': 0.15
}

multi_result = runner.run_strategy(
    "MultiFactorStrategy", factor_data, price_data,
    parameters={"momentum_weight": 0.3, "value_weight": 0.2,
                "quality_weight": 0.2, "volatility_weight": 0.15,
                "size_weight": 0.15}
)
```

### 5. 均值回归策略 (Mean Reversion Strategy)

**核心理念**: 价格偏离均值后会回归

**策略逻辑**:
- RSI < 30 (超卖)
- 20天动量在-20%到0%之间
- 波动率 < 40%
- 短期持有

**适用条件**:
- 震荡市场
- 个股基本面稳定
- 技术分析有效

**风险提示**:
- 趋势延续风险
- 需要精确时机
- 止损要求严格

```python
# 均值回归策略示例
reversion_result = runner.run_strategy(
    "MeanReversionStrategy", factor_data, price_data,
    parameters={"rsi_oversold": 30.0,      # RSI < 30
                "rsi_overbought": 70.0,    # RSI > 70
                "max_volatility": 40.0}
)
```

### 6. 低波动策略 (Low Volatility Strategy)

**核心理念**: 低波动股票长期表现更好

**策略逻辑**:
- 波动率 < 15%
- 股息率 > 1.5%
- 负债率 < 60%
- 防御性配置

**适用条件**:
- 市场不确定性高
- 熊市或震荡市
- 风险偏好低

**风险提示**:
- 可能错过牛市
- 收益相对较低
- 需要长期持有

> ⚠️ **尚未内置 (Not yet a builtin)** — 低波动策略为设计概念，需自行实现。
> 继承 `StrategyBase` 并实现 `generate_signals(factor_data, price_data)`，
> 然后用 `StrategyRegistry().register_strategy(LowVolatilityStrategy)` 注册。

```python
# 低波动策略 — 自定义实现骨架
from data_service.strategies import StrategyBase, StrategyResult, StrategyRegistry

class LowVolatilityStrategy(StrategyBase):
    def __init__(self):
        super().__init__("LowVolatilityStrategy", "选择低波动、高股息的防御股")
    def generate_signals(self, factor_data, price_data, **kw) -> StrategyResult:
        ...   # 基于 price_volatility / dividend_yield 因子筛选并加权

StrategyRegistry().register_strategy(LowVolatilityStrategy)
```

### 7. 行业轮动策略 (Sector Rotation Strategy)

**核心理念**: 不同经济周期下行业表现不同

**策略逻辑**:
- 选择动量最强的3个行业
- 每个行业选择前5只股票
- 等权重配置
- 月度调仓

**适用条件**:
- 经济周期明显
- 行业数据完整
- 宏观分析能力强

**风险提示**:
- 行业集中度风险
- 需要宏观判断
- 换手率很高

> ⚠️ **尚未内置 (Not yet a builtin)** — 行业轮动策略为设计概念。需要额外的
> 行业 (`sector`) 数据，可继承 `StrategyBase` 自行实现并注册。

```python
# 行业轮动策略 — 自定义实现骨架
class SectorRotationStrategy(StrategyBase):
    def __init__(self):
        super().__init__("SectorRotationStrategy", "选择动量最强行业的龙头股")
    def generate_signals(self, factor_data, price_data, **kw) -> StrategyResult:
        ...   # 按行业聚合动量, 选 top 行业再选行业内 top 股票

StrategyRegistry().register_strategy(SectorRotationStrategy)
```

### 8. 风险平价策略 (Risk Parity Strategy)

**核心理念**: 每个持仓贡献相等的风险

**策略逻辑**:
- 基于波动率分配权重
- 目标组合波动率10%
- 质量筛选
- 动态调整

**适用条件**:
- 风险控制要求高
- 数据质量良好
- 计算能力强

**风险提示**:
- 可能过度集中
- 需要精确计算
- 调仓成本较高

> ⚠️ **尚未内置 (Not yet a builtin)** — 风险平价策略为设计概念。可继承
> `StrategyBase`，按波动率倒数分配权重，自行实现并注册。

```python
# 风险平价策略 — 自定义实现骨架
class RiskParityStrategy(StrategyBase):
    def __init__(self):
        super().__init__("RiskParityStrategy", "按风险贡献相等分配权重")
    def generate_signals(self, factor_data, price_data, **kw) -> StrategyResult:
        ...   # weight_i ∝ 1 / volatility_i, 归一化到目标组合波动率

StrategyRegistry().register_strategy(RiskParityStrategy)
```

## 🚀 策略组合建议

### 保守型组合
- 低波动策略 40%
- 价值策略 30%
- 风险平价策略 30%

### 平衡型组合
- 多因子策略 40%
- 质量成长策略 30%
- 动量策略 30%

### 进取型组合
- 动量策略 40%
- 行业轮动策略 30%
- 均值回归策略 30%

## 📈 策略评估指标

### 收益指标
- **年化收益率**: 策略的年化收益
- **超额收益**: 相对于基准的超额收益
- **信息比率**: 超额收益/跟踪误差

### 风险指标
- **最大回撤**: 最大亏损幅度
- **波动率**: 收益的标准差
- **VaR**: 在险价值

### 其他指标
- **夏普比率**: 风险调整后收益
- **胜率**: 正收益天数占比
- **换手率**: 策略调仓频率

## ⚠️ 风险提示

1. **历史表现不代表未来**: 所有策略都基于历史数据，未来表现可能不同
2. **市场环境变化**: 不同市场环境下策略表现差异很大
3. **数据质量**: 策略效果很大程度上依赖于数据质量
4. **交易成本**: 频繁调仓会产生较高的交易成本
5. **流动性风险**: 某些股票可能存在流动性不足的问题

## 🔧 策略优化建议

### 参数优化
- 使用交叉验证避免过拟合
- 定期重新优化参数
- 考虑市场环境变化

### 风险控制
- 设置止损条件
- 控制单只股票权重
- 监控相关性变化

### 执行优化
- 考虑交易成本
- 优化调仓时机
- 使用算法交易

## 📊 回测结果示例

```
============================================================
QUANTITATIVE STRATEGY COMPARISON REPORT
============================================================

📊 Momentum Strategy
----------------------------------------
Selected Stocks: 20
Top 5 Stocks: AAPL, GOOGL, MSFT, AMZN, TSLA
Sharpe Ratio: 1.25
Win Rate: 58.5%
Max Drawdown: -12.3%

📊 Value Strategy
----------------------------------------
Selected Stocks: 30
Top 5 Stocks: JNJ, PG, KO, WMT, MCD
Sharpe Ratio: 0.95
Win Rate: 52.1%
Max Drawdown: -8.7%

📊 Multi-Factor Strategy
----------------------------------------
Selected Stocks: 25
Top 5 Stocks: AAPL, JNJ, GOOGL, PG, MSFT
Sharpe Ratio: 1.45
Win Rate: 61.2%
Max Drawdown: -9.8%
```

## 🎯 使用建议

1. **选择适合的策略**: 根据投资目标和风险偏好选择
2. **组合使用**: 可以组合多个策略分散风险
3. **定期评估**: 定期评估策略表现并调整
4. **风险控制**: 始终把风险控制放在首位
5. **持续学习**: 市场在变化，策略也需要进化

这些策略为量化投资提供了完整的工具集，你可以根据自己的需求进行选择和组合使用！ 
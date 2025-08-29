# RGB灯光控制原理详解

本文档详细解释了 `test_rgb.py` 脚本中如何控制Focus Lamp的RGB灯光颜色和亮度。

## 1. 系统架构概述

Focus Lamp的RGB灯光控制系统采用了基于事件驱动的服务架构：

```
test_rgb.py → RGBService → WS2812B LED灯带
```

## 2. 核心组件分析

### 2.1 RGBService类

`RGBService` 是RGB灯光控制的核心服务类，继承自 `ServiceBase`，具有以下特性：

#### 初始化参数
```python
def __init__(self, 
             led_count: int = 40,        # LED数量，默认40个
             led_pin: int = 12,          # GPIO引脚号
             led_freq_hz: int = 800000,  # 信号频率800kHz
             led_dma: int = 10,          # DMA通道
             led_brightness: int = 255,  # 全局亮度(0-255)
             led_invert: bool = False,   # 信号反转
             led_channel: int = 0):      # PWM通道
```

#### 硬件控制
- 使用 `rpi_ws281x` 库控制WS2812B LED灯带
- 支持40个可独立控制的RGB LED
- 通过GPIO 12引脚发送数据信号

### 2.2 优先级系统

系统实现了4级优先级机制：
```python
class Priority(IntEnum):
    CRITICAL = 0  # 最高优先级
    HIGH = 1      # 高优先级  
    NORMAL = 2    # 普通优先级(默认)
    LOW = 3       # 低优先级
```

**优先级工作原理：**
- 高优先级事件可以中断低优先级事件
- 同等优先级事件按时间顺序执行
- 在test_rgb.py中演示了高优先级红色覆盖白色paint模式

## 3. 颜色控制机制

### 3.1 颜色表示方法

RGB颜色使用两种格式：
1. **RGB元组**: `(R, G, B)` - 每个分量范围0-255
2. **整数值**: 直接传入Color对象的整数值

### 3.2 颜色转换过程

```python
# 元组转换为Color对象
if isinstance(color_code, tuple) and len(color_code) == 3:
    color = Color(color_code[0], color_code[1], color_code[2])
```

**Color函数参数顺序**: `Color(red, green, blue)`

### 3.3 亮度控制

#### 全局亮度控制
- 通过初始化参数 `led_brightness` 设置(0-255)
- 影响所有LED的整体亮度
- 在硬件层面实现，不影响颜色比例

#### 颜色分量亮度控制
- 通过调整RGB各分量值实现
- 例如：`(255, 0, 0)` 最亮红色，`(128, 0, 0)` 半亮度红色

## 4. 控制模式详解

### 4.1 Solid模式 - 单色填充

```python
rgb_service.dispatch("solid", (255, 0, 0))  # 全部LED显示红色
```

**工作流程：**
1. 接收颜色参数
2. 遍历所有40个LED
3. 设置每个LED为相同颜色
4. 调用 `strip.show()` 更新显示

**代码实现：**
```python
def _handle_solid(self, color_code):
    color = Color(color_code[0], color_code[1], color_code[2])
    for i in range(self.led_count):  # 遍历40个LED
        self.strip.setPixelColor(i, color)
    self.strip.show()  # 立即更新显示
```

### 4.2 Paint模式 - 多色模式

```python
colors = [(255,0,0), (0,255,0), (0,0,255)]  # 红绿蓝序列
rgb_service.dispatch("paint", colors)
```

**工作流程：**
1. 接收颜色数组
2. 逐个设置LED颜色
3. 支持不同LED显示不同颜色
4. 数组长度可小于LED数量

**代码实现：**
```python
def _handle_paint(self, colors):
    max_pixels = min(len(colors), self.led_count)
    for i in range(max_pixels):
        color = Color(colors[i][0], colors[i][1], colors[i][2])
        self.strip.setPixelColor(i, color)
    self.strip.show()
```

## 5. test_rgb.py测试流程分析

### 5.1 基础颜色测试
```python
# 测试三原色，每种颜色显示2秒
rgb_service.dispatch("solid", (255, 0, 0))    # 红色
time.sleep(2)
rgb_service.dispatch("solid", (0, 255, 0))    # 绿色  
time.sleep(2)
rgb_service.dispatch("solid", (0, 0, 255))    # 蓝色
time.sleep(2)
```

### 5.2 多色模式测试
```python
colors = [
    (255, 0, 0),    # 红色
    (0, 255, 0),    # 绿色
    (0, 0, 255),    # 蓝色
    (255, 255, 0),  # 黄色
    (255, 0, 255),  # 洋红色
] * 8  # 重复8次，填满40个LED

rgb_service.dispatch("paint", colors)
```

### 5.3 优先级测试
```python
# 先设置白色paint模式
rgb_service.dispatch("paint", [(255, 255, 255)] * 40)
# 高优先级红色会立即覆盖白色
rgb_service.dispatch("solid", (255, 0, 0), Priority.HIGH)
```

## 6. 技术要点总结

### 6.1 硬件特性
- **LED类型**: WS2812B可编程RGB LED
- **数据传输**: 单线串行协议，800kHz频率
- **颜色深度**: 每个颜色分量8位(0-255)
- **LED数量**: 40个可独立控制

### 6.2 软件特性
- **异步处理**: 基于线程的事件循环
- **优先级队列**: 支持事件优先级管理
- **错误处理**: 完善的异常捕获和日志记录
- **资源管理**: 自动清理和安全停止

### 6.3 性能优化
- **批量更新**: 所有LED设置完成后统一调用show()
- **内存效率**: 重用Color对象，避免频繁创建
- **线程安全**: 使用锁机制保护共享资源

## 7. 实际应用场景

1. **状态指示**: 不同颜色表示设备不同状态
2. **情感表达**: 通过颜色变化表达情感
3. **视觉反馈**: 响应用户操作的即时反馈
4. **环境氛围**: 营造特定的光照氛围

通过这套系统，Focus Lamp能够实现丰富的视觉效果，为用户提供直观的状态反馈和良好的交互体验。
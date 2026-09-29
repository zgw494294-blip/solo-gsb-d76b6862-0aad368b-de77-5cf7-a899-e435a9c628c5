# 离线测距定位（FastAPI + 原生 HTML/CSS/JavaScript）

完全离线运行的测距定位演示页面。用户录入坐标上界与若干信标的位置和欧氏距离读数区间，系统在 **0～N 的网格整数点** 上枚举所有可能位置，并在网格图上标出搜索区域。

## 一条命令启动（推荐，使用 Docker Compose）

```bash
docker compose up --build
```

启动后用浏览器访问：

> **http://localhost:8000**

停止：`docker compose down`。

## 不用 Docker 时本地启动

需要 Python 3.10+：

```bash
python -m venv .venv
source .venv/bin/activate          # Windows 为 .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 **http://localhost:8000**。

## 定位规则

- 坐标上界 N 为 **2～40** 的整数，网格点坐标满足 `0 ≤ x,y ≤ N`（共 (N+1)² 个点）。
- 录入 **3～8** 个信标，每个信标包含：
  - 唯一 ID（非空、不可与其他信标重复）；
  - 整数坐标 (x, y)，必须在 `0～N` 内；
  - 非负整数距离闭区间 `[dmin, dmax]`，且 `dmin ≤ dmax`。
- 点到信标按**欧氏距离**计算，边界也算符合：
  `dmin² ≤ (x−xᵦ)² + (y−yᵦ)² ≤ dmax²`

求解过程：

1. 先枚举与**全部读数**一致的点。若存在，只展示这一组结果（按四邻接即上/下/左/右划分搜索区域）。
2. 若不存在，则**依次只排除一条读数**，分别求其余读数共同允许的点；每一种成立的排除都作为独立假设保留，**不同假设只做颜色叠加，绝不合并成同一片位置**；不成立的排除（无候选点）直接丢弃。
3. 若所有排除都不成立，显示「无法定位」。
4. 修改任意读数后立即作废旧结果并自动重算（防抖 300ms），重算期间图上会显示「旧结果已失效」遮罩。
5. 无效区间、越界坐标、重复 ID、信标数量不符等情况会逐条说明原因，并标红对应输入框。

## 页面与接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 定位页面（原生 HTML/CSS/JS，无任何外部 CDN 依赖） |
| POST | `/api/locate` | 提交 `{n, beacons:[{id,x,y,dmin,dmax}]}`，返回定位结果；输入非法返回 422 与逐字段错误 |
| GET | `/api/health` | 健康检查 |

响应状态：

- `located`：全部读数一致，给出候选点与四邻接区域；
- `ambiguous_excluded`：全部读数无交点，给出所有成立的“排除一条读数”假设；
- `unlocatable`：所有假设都不成立，无法定位。

## 项目结构

```
.
├── app/
│   ├── __init__.py
│   ├── locating.py     # 校验、枚举、四邻接分区等核心算法
│   └── main.py         # FastAPI 入口与静态页面托管
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── tests/
│   └── test_locating.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 运行测试

```bash
python -m unittest discover -s tests -v
```

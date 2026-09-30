"""离线测距定位的核心求解逻辑。

目标只可能落在 0..N 的网格整数点上。每个信标给出欧氏距离的非负整数
闭区间 [dmin, dmax]（边界也算符合）：

    dmin^2 <= (x - xb)^2 + (y - yb)^2 <= dmax^2

先求与全部读数一致的点；若不存在，则依次排除一条读数，分别求其余读数
共同允许的点。每种假设的候选点再按四邻接（上下左右）划分为若干搜索
区域，不同假设的结果绝不合并。
"""

MIN_N = 2
MAX_N = 40
MIN_BEACONS = 3
MAX_BEACONS = 8
MAX_STEPS = 200


def to_int(value):
    """严格整数解析：JSON 中必须是整数（不接受浮点数/布尔值），
    字符串必须整体是一个整数（允许前后空白与正负号）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip('+-').isdigit():
            try:
                return int(text)
            except ValueError:
                return None
    return None


def validate_payload(payload):
    """校验请求体，返回 (n, beacons, errors)。errors 为空时校验通过。"""
    errors = {}

    if not isinstance(payload, dict):
        return None, None, {'_': '请求体必须是 JSON 对象'}

    n = to_int(payload.get('n'))
    if n is None:
        errors['n'] = '坐标上界 N 必须是整数'
    elif not (MIN_N <= n <= MAX_N):
        errors['n'] = f'坐标上界 N 必须在 {MIN_N}～{MAX_N} 之间'

    raw_beacons = payload.get('beacons')
    if not isinstance(raw_beacons, list):
        errors['beacons'] = '信标列表缺失或格式无效'
        return None, None, errors

    count = len(raw_beacons)
    if not (MIN_BEACONS <= count <= MAX_BEACONS):
        errors['beacons'] = (
            f'信标数量必须为 {MIN_BEACONS}～{MAX_BEACONS} 个，当前为 {count} 个'
        )

    beacons = []
    seen_ids = {}
    for i, raw in enumerate(raw_beacons):
        prefix = f'beacons.{i}'
        if not isinstance(raw, dict):
            errors[prefix] = '信标格式无效'
            continue

        row_errors = {}

        bid = None
        raw_id = raw.get('id')
        if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
            row_errors['id'] = '信标 ID 不能为空'
        else:
            bid = raw_id.strip() if isinstance(raw_id, str) else str(raw_id)
            if bid in seen_ids:
                row_errors['id'] = f'ID 与第 {seen_ids[bid] + 1} 个信标重复，ID 必须唯一'
                bid = None
            else:
                seen_ids[bid] = i

        x = to_int(raw.get('x'))
        if x is None:
            row_errors['x'] = 'x 必须是整数'
        elif n is not None and not (0 <= x <= n):
            row_errors['x'] = f'x 越界，必须在 0～{n} 之间'

        y = to_int(raw.get('y'))
        if y is None:
            row_errors['y'] = 'y 必须是整数'
        elif n is not None and not (0 <= y <= n):
            row_errors['y'] = f'y 越界，必须在 0～{n} 之间'

        dmin = to_int(raw.get('dmin'))
        if dmin is None:
            row_errors['dmin'] = '距离下界必须是非负整数'
        elif dmin < 0:
            row_errors['dmin'] = '距离下界不能为负'

        dmax = to_int(raw.get('dmax'))
        if dmax is None:
            row_errors['dmax'] = '距离上界必须是非负整数'
        elif dmax < 0:
            row_errors['dmax'] = '距离上界不能为负'

        if dmin is not None and dmax is not None and dmin > dmax:
            row_errors['dmin'] = '距离闭区间无效：下界不能大于上界'

        for sub, message in row_errors.items():
            errors[f'{prefix}.{sub}'] = message

        if not row_errors:
            beacons.append({
                'id': bid,
                'x': x,
                'y': y,
                'dmin': dmin,
                'dmax': dmax,
            })

    return (n if not errors else None), (beacons if not errors else None), errors


def validate_suggest_payload(payload):
    """校验复测布点请求体。

    复用定位请求的 n / beacons 校验，额外校验当前所在整数格点
    (originX, originY) 与可走步数 maxSteps。返回 (n, beacons, origin,
    max_steps, errors)。"""
    n, beacons, errors = validate_payload(payload)

    if not isinstance(payload, dict):
        return None, None, None, None, errors

    origin = [None, None]
    for axis, key in (('x', 'originX'), ('y', 'originY')):
        value = to_int(payload.get(key))
        label = '起点 x' if axis == 'x' else '起点 y'
        if value is None:
            errors[key] = f'{label} 必须是整数'
        elif n is not None and not (0 <= value <= n):
            errors[key] = f'{label} 越界，必须在 0～{n} 之间'
        else:
            origin[0 if axis == 'x' else 1] = value

    max_steps = to_int(payload.get('maxSteps'))
    if max_steps is None:
        errors['maxSteps'] = '可走步数必须是非负整数'
    elif max_steps < 0:
        errors['maxSteps'] = '可走步数不能为负'
    elif max_steps > MAX_STEPS:
        errors['maxSteps'] = f'可走步数不能超过 {MAX_STEPS}'

    if errors:
        return None, None, None, None, errors
    return n, beacons, tuple(origin), max_steps, errors


def allowed_points(beacons, n):
    """枚举网格中同时满足给定信标全部距离区间的整数点。"""
    points = []
    for y in range(n + 1):
        for x in range(n + 1):
            for b in beacons:
                dist_sq = (x - b['x']) ** 2 + (y - b['y']) ** 2
                if not (b['dmin'] ** 2 <= dist_sq <= b['dmax'] ** 2):
                    break
            else:
                points.append((x, y))
    return points


def split_regions(points):
    """按四邻接（上/下/左/右）把候选点划分为若干连通区域。

    区域内点按 y 降序、x 升序排列（最靠上、最靠左的点在前）；
    区域之间按点数降序、再按首点坐标排序，保证输出稳定。"""
    pool = set(points)
    regions = []
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1))

    while pool:
        start = pool.pop()
        stack = [start]
        region = []
        while stack:
            x, y = stack.pop()
            region.append((x, y))
            for dx, dy in directions:
                neighbor = (x + dx, y + dy)
                if neighbor in pool:
                    pool.discard(neighbor)
                    stack.append(neighbor)
        region.sort(key=lambda p: (-p[1], p[0]))
        regions.append(region)

    regions.sort(key=lambda r: (-len(r), r[0][1], -r[0][0]))
    return [[{'x': x, 'y': y} for x, y in region] for region in regions]


def make_hypothesis(excluded_index, excluded_id, beacons, n):
    points = allowed_points(beacons, n)
    if not points:
        return None
    regions = split_regions(points)
    return {
        'excludedIndex': excluded_index,
        'excludedId': excluded_id,
        'regionCount': len(regions),
        'pointCount': len(points),
        'regions': regions,
    }


def solve(n, beacons):
    """返回定位结果：located / ambiguous_excluded / unlocatable。"""
    full = make_hypothesis(None, None, beacons, n)

    if full is not None:
        return {
            'status': 'located',
            'n': n,
            'beacons': beacons,
            'hypotheses': [full],
        }

    hypotheses = []
    for i, beacon in enumerate(beacons):
        rest = beacons[:i] + beacons[i + 1:]
        hypothesis = make_hypothesis(i, beacon['id'], rest, n)
        if hypothesis is not None:
            hypotheses.append(hypothesis)

    return {
        'status': 'ambiguous_excluded' if hypotheses else 'unlocatable',
        'n': n,
        'beacons': beacons,
        'hypotheses': hypotheses,
    }


def hypothesis_points(hypothesis):
    """展平一个假设的各区域，返回其全部候选点 (x, y)。"""
    return [
        (point['x'], point['y'])
        for region in hypothesis['regions']
        for point in region
    ]


def candidate_sites(n, beacons, origin, max_steps):
    """枚举可达且未放置信标的网格点：曼哈顿距离不超过 max_steps。

    按 (y, x) 升序生成，后续并列选择时天然满足 y、x 的次序要求。"""
    ox, oy = origin
    occupied = {(b['x'], b['y']) for b in beacons}
    for y in range(max(0, oy - max_steps), min(n, oy + max_steps) + 1):
        remain = max_steps - abs(y - oy)
        for x in range(max(0, ox - remain), min(n, ox + remain) + 1):
            if (x, y) not in occupied:
                yield x, y


def build_suggestion(n, beacons, origin, max_steps):
    """基于 solve 的结果推荐一个复测布点。

    把求解器每个成立假设的每个候选点都视为一种“目标真实位置”情形；
    复测在候选点 (px,py) 处精确给出 d²=(x−px)²+(y−py)²，同一读数对应的
    情形无法区分，构成一个读数分组。优先使最大分组最小，并列时选曼哈顿
    步数最少，再按 y、x 升序。"""
    result = solve(n, beacons)
    status = result['status']
    hypotheses = result['hypotheses']

    base = {
        'n': n,
        'beacons': beacons,
        'originX': origin[0],
        'originY': origin[1],
        'maxSteps': max_steps,
        'locateStatus': status,
        'hypotheses': hypotheses,
    }

    if status == 'unlocatable':
        return dict(base, status='unlocatable', reason=(
            '现有读数下不存在任何成立的假设（全部读数及其任一排他组合都没有 '
            '共同允许的网格点），没有可供复测区分的情形。请先检查读数是否录入有误。'
        ))

    # 坐标 -> 覆盖该点的假设下标（同一坐标可被多个假设同时允许，算多种情形）
    multiplicity = {}
    for hi, hypothesis in enumerate(hypotheses):
        for point in hypothesis_points(hypothesis):
            multiplicity.setdefault(point, []).append(hi)

    total_cases = sum(len(his) for his in multiplicity.values())

    if status == 'located' and total_cases <= 1:
        return dict(base, status='already_unique', totalCases=total_cases, reason=(
            '全部读数一致且候选点只有 1 个，目标位置已唯一确定，无需复测。'
        ))

    ox, oy = origin
    sites = list(candidate_sites(n, beacons, origin, max_steps))
    if not sites:
        return dict(base, status='no_site', totalCases=total_cases, reason=(
            f'从当前格点 ({ox},{oy}) 出发、曼哈顿距离不超过 {max_steps} 步的'
            '可达网格点均已放置信标，没有可用的复测布点。'
            '请增大可走步数，或把起点移到未放信标的格点。'
        ))

    best = None  # (最大组大小, 步数, y, x)
    best_buckets = None
    for px, py in sites:
        buckets = {}
        for (tx, ty), his in multiplicity.items():
            reading = (tx - px) ** 2 + (ty - py) ** 2
            buckets.setdefault(reading, 0)
            buckets[reading] += len(his)
        worst = max(buckets.values())
        key = (worst, abs(px - ox) + abs(py - oy), py, px)
        if best is None or key < best:
            best = key
            best_buckets = buckets

    worst, steps, py, px = best

    # 重新整理推荐点的读数分组详情：读数 -> [{hypothesis, points}]
    groups = {}
    for hi, hypothesis in enumerate(hypotheses):
        for tx, ty in hypothesis_points(hypothesis):
            reading = (tx - px) ** 2 + (ty - py) ** 2
            groups.setdefault(reading, {}).setdefault(hi, []).append((tx, ty))

    readings = []
    for reading in sorted(groups):
        members = []
        for hi in sorted(groups[reading]):
            pts = sorted(groups[reading][hi], key=lambda p: (-p[1], p[0]))
            members.append({
                'hypothesisIndex': hi,
                'excludedIndex': hypotheses[hi]['excludedIndex'],
                'excludedId': hypotheses[hi]['excludedId'],
                'points': [{'x': x, 'y': y} for x, y in pts],
            })
        readings.append({
            'reading': reading,
            'caseCount': sum(len(m['points']) for m in members),
            'members': members,
        })

    return dict(base, status='recommended', totalCases=total_cases,
                candidateCount=len(sites), recommendation={
                    'x': px,
                    'y': py,
                    'steps': steps,
                    'worstCases': worst,
                    'readingCount': len(readings),
                    'readings': readings,
                })

import unittest

from app.locating import (
    allowed_points,
    build_suggestion,
    candidate_sites,
    hypothesis_points,
    solve,
    split_regions,
    to_int,
    validate_payload,
    validate_suggest_payload,
)


class TestToInt(unittest.TestCase):
    def test_values(self):
        self.assertEqual(to_int(3), 3)
        self.assertEqual(to_int(' -4 '), -4)
        self.assertIsNone(to_int(1.5))
        self.assertIsNone(to_int(True))
        self.assertIsNone(to_int('1.0'))
        self.assertIsNone(to_int('abc'))
        self.assertIsNone(to_int(None))


def beacon(bid, x, y, dmin, dmax):
    return {'id': bid, 'x': x, 'y': y, 'dmin': dmin, 'dmax': dmax}


class TestValidate(unittest.TestCase):
    def test_ok(self):
        payload = {'n': 10, 'beacons': [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 10, 10, 0, 30),
            beacon('C', 5, 5, 1, 2),
        ]}
        n, beacons, errors = validate_payload(payload)
        self.assertEqual(n, 10)
        self.assertEqual(len(beacons), 3)
        self.assertEqual(errors, {})

    def test_n_out_of_range(self):
        _, _, errors = validate_payload({'n': 1, 'beacons': []})
        self.assertIn('n', errors)
        _, _, errors = validate_payload({'n': 41, 'beacons': []})
        self.assertIn('n', errors)

    def test_wrong_count(self):
        _, _, errors = validate_payload({'n': 5, 'beacons': [
            beacon('A', 0, 0, 0, 0), beacon('B', 1, 0, 0, 0),
        ]})
        self.assertIn('beacons', errors)

    def test_duplicate_id(self):
        _, _, errors = validate_payload({'n': 5, 'beacons': [
            beacon('A', 0, 0, 0, 0),
            beacon('A', 1, 0, 0, 0),
            beacon('C', 2, 0, 0, 0),
        ]})
        self.assertIn('beacons.1.id', errors)

    def test_empty_id(self):
        _, _, errors = validate_payload({'n': 5, 'beacons': [
            beacon('  ', 0, 0, 0, 0),
            beacon('B', 1, 0, 0, 0),
            beacon('C', 2, 0, 0, 0),
        ]})
        self.assertIn('beacons.0.id', errors)

    def test_out_of_grid(self):
        _, _, errors = validate_payload({'n': 5, 'beacons': [
            beacon('A', 6, 0, 0, 0),
            beacon('B', -1, 0, 0, 0),
            beacon('C', 0, 9, 0, 0),
        ]})
        self.assertIn('beacons.0.x', errors)
        self.assertIn('beacons.1.x', errors)
        self.assertIn('beacons.2.y', errors)

    def test_bad_interval(self):
        _, _, errors = validate_payload({'n': 5, 'beacons': [
            beacon('A', 0, 0, 3, 2),
            beacon('B', 1, 0, -1, 0),
            beacon('C', 2, 0, 0, -2),
        ]})
        self.assertIn('beacons.0.dmin', errors)
        self.assertIn('beacons.1.dmin', errors)
        self.assertIn('beacons.2.dmax', errors)

    def test_string_integers_accepted(self):
        n, beacons, errors = validate_payload({'n': '6', 'beacons': [
            beacon('A', '0', '0', '0', '0'),
            beacon('B', '6', '6', '1', '3'),
            beacon('C', '3', '0', '2', '4'),
        ]})
        self.assertEqual(n, 6)
        self.assertEqual(beacons[0], {'id': 'A', 'x': 0, 'y': 0, 'dmin': 0, 'dmax': 0})
        self.assertEqual(errors, {})

    def test_float_rejected(self):
        _, _, errors = validate_payload({'n': 5.5, 'beacons': [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 1, 0, 0, 0),
            beacon('C', 2, 0, 0, 0),
        ]})
        self.assertIn('n', errors)


class TestGeometry(unittest.TestCase):
    def test_zero_distance_pins_point(self):
        points = allowed_points([beacon('A', 3, 4, 0, 0)], 10)
        self.assertEqual(points, [(3, 4)])

    def test_boundary_inclusive(self):
        # (3,4) 到原点距离恰为 5，闭区间 [5,5] 必须包含边界
        points = allowed_points([beacon('A', 0, 0, 5, 5)], 10)
        self.assertIn((3, 4), points)
        self.assertNotIn((3, 3), points)  # 距离 sqrt(18)≈4.24，不符合

    def test_disk_contains_origin(self):
        points = allowed_points([beacon('A', 0, 0, 0, 1)], 2)
        # (1,1) 距离 √2 > 1，不属于；距离边界 1 的 (0,1)/(1,0) 属于
        self.assertEqual(sorted(points), [(0, 0), (0, 1), (1, 0)])


class TestRegions(unittest.TestCase):
    def test_four_connectivity_only(self):
        # (0,0)-(1,0) 相连；(3,0) 独立；(2,1) 与 (1,0) 仅对角，不算连通
        regions = split_regions([(0, 0), (1, 0), (3, 0), (2, 1)])
        sizes = sorted(len(r) for r in regions)
        self.assertEqual(sizes, [1, 1, 2])

    def test_region_point_ordering(self):
        regions = split_regions([(0, 0), (0, 1)])
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0][0], {'x': 0, 'y': 1})  # 最上点在前


class TestSolve(unittest.TestCase):
    def test_located_unique_point(self):
        # 到 (0,0) 与 (10,0) 距离都恰为 5 的整数点只有 (5,0)；
        # 它到 (5,3) 距离恰为 3。
        result = solve(10, [
            beacon('A', 0, 0, 5, 5),
            beacon('B', 10, 0, 5, 5),
            beacon('C', 5, 3, 3, 3),
        ])
        self.assertEqual(result['status'], 'located')
        h = result['hypotheses'][0]
        self.assertIsNone(h['excludedIndex'])
        self.assertEqual(h['pointCount'], 1)
        self.assertEqual(h['regions'], [[{'x': 5, 'y': 0}]])

    def test_two_independent_hypotheses_are_not_merged(self):
        # A 钉死原点，B 钉死 (5,0)，C 在 (0,5) 给宽区间 [0,10]。
        # 三者无交点；排除 A -> B∩C 含 (5,0)；排除 B -> A∩C 含 (0,0)；
        # 排除 C -> A、B 互斥，假设不成立。
        result = solve(10, [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 5, 0, 0, 0),
            beacon('C', 0, 5, 0, 10),
        ])
        self.assertEqual(result['status'], 'ambiguous_excluded')
        self.assertEqual(len(result['hypotheses']), 2)

        first_points = {(p['x'], p['y'])
                        for r in result['hypotheses'][0]['regions'] for p in r}
        second_points = {(p['x'], p['y'])
                         for r in result['hypotheses'][1]['regions'] for p in r}
        # 两个假设各自独立，保留为两个 hypothesis，绝不合并
        self.assertTrue(first_points == {(5, 0)} or first_points == {(0, 0)})
        self.assertTrue(second_points == {(5, 0)} or second_points == {(0, 0)})
        self.assertNotEqual(first_points, second_points)

    def test_hypothesis_splits_into_disconnected_regions(self):
        # B 要求距原点恰为 2（整数点 (2,0)、(0,2)）；C=(2,2) 给 [0,3]，
        # 两点到 C 距离都是 2，且彼此仅对角 -> 同一假设内必须分成两个区域。
        # A=(20,20) 零距离钉死，与 B、C 全部矛盾。
        result = solve(20, [
            beacon('A', 20, 20, 0, 0),
            beacon('B', 0, 0, 2, 2),
            beacon('C', 2, 2, 0, 3),
        ])
        self.assertEqual(result['status'], 'ambiguous_excluded')
        self.assertEqual(len(result['hypotheses']), 1)
        h = result['hypotheses'][0]
        self.assertEqual(h['excludedId'], 'A')
        self.assertEqual(h['pointCount'], 2)
        self.assertEqual(h['regionCount'], 2)
        self.assertEqual([len(r) for r in h['regions']], [1, 1])

    def test_unlocatable(self):
        # 三个互斥的零距离点：任意两条读数都没有共同允许点
        result = solve(6, [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 6, 0, 0, 0),
            beacon('C', 6, 6, 0, 0),
        ])
        self.assertEqual(result['status'], 'unlocatable')
        self.assertEqual(result['hypotheses'], [])

    def test_regions_partition_points(self):
        result = solve(10, [
            beacon('A', 2, 2, 1, 4),
            beacon('B', 8, 3, 2, 5),
            beacon('C', 5, 9, 1, 5),
        ])
        for h in result['hypotheses']:
            total = sum(len(r) for r in h['regions'])
            self.assertEqual(total, h['pointCount'])


def all_cases(result):
    """求解结果中的全部情形：(假设下标, (x, y))，同点多假设各算一种。"""
    cases = []
    for hi, hypothesis in enumerate(result['hypotheses']):
        for region in hypothesis['regions']:
            for point in region:
                cases.append((hi, (point['x'], point['y'])))
    return cases


def brute_force_worst(cases, px, py):
    buckets = {}
    for _, (tx, ty) in cases:
        reading = (tx - px) ** 2 + (ty - py) ** 2
        buckets[reading] = buckets.get(reading, 0) + 1
    return max(buckets.values())


class TestSuggestValidation(unittest.TestCase):
    def test_ok(self):
        payload = {'n': 10, 'originX': 2, 'originY': '3', 'maxSteps': 4,
                   'beacons': [
                       beacon('A', 0, 0, 0, 0),
                       beacon('B', 10, 10, 0, 30),
                       beacon('C', 5, 5, 1, 2),
                   ]}
        n, beacons, origin, max_steps, errors = validate_suggest_payload(payload)
        self.assertEqual(errors, {})
        self.assertEqual((n, origin, max_steps), (10, (2, 3), 4))

    def test_bad_origin_and_steps(self):
        payload = {'n': 5, 'originX': 6, 'originY': -1, 'maxSteps': -1,
                   'beacons': [
                       beacon('A', 0, 0, 0, 0),
                       beacon('B', 1, 0, 0, 0),
                       beacon('C', 2, 0, 0, 0),
                   ]}
        _, _, _, _, errors = validate_suggest_payload(payload)
        self.assertIn('originX', errors)
        self.assertIn('originY', errors)
        self.assertIn('maxSteps', errors)

    def test_beacon_errors_propagate(self):
        payload = {'n': 5, 'originX': 0, 'originY': 0, 'maxSteps': 1,
                   'beacons': [beacon('A', 0, 0, 0, 0)]}
        _, _, _, _, errors = validate_suggest_payload(payload)
        self.assertIn('beacons', errors)


class TestCandidateSites(unittest.TestCase):
    def test_diamond_and_beacon_exclusion(self):
        beacons = [beacon('A', 2, 2, 0, 0), beacon('B', 1, 2, 0, 0)]
        sites = list(candidate_sites(5, beacons, (2, 2), 1))
        # 距 (2,2) 曼哈顿不超过 1 的 5 个格点，去掉 2 个信标点
        self.assertEqual(sorted(sites), [(2, 1), (2, 3), (3, 2)])

    def test_clipped_by_grid(self):
        sites = set(candidate_sites(3, [], (0, 0), 10))
        self.assertEqual(sites, {(x, y) for x in range(4) for y in range(4)})

    def test_zero_steps_on_beacon_means_no_site(self):
        beacons = [beacon('A', 1, 1, 0, 0)]
        self.assertEqual(list(candidate_sites(3, beacons, (1, 1), 0)), [])


class TestSuggest(unittest.TestCase):
    def test_already_unique(self):
        result = build_suggestion(10, [
            beacon('A', 0, 0, 5, 5),
            beacon('B', 10, 0, 5, 5),
            beacon('C', 5, 3, 3, 3),
        ], (5, 0), 3)
        self.assertEqual(result['status'], 'already_unique')
        self.assertEqual(result['totalCases'], 1)
        self.assertNotIn('recommendation', result)

    def test_unlocatable(self):
        result = build_suggestion(6, [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 6, 0, 0, 0),
            beacon('C', 6, 6, 0, 0),
        ], (0, 0), 3)
        self.assertEqual(result['status'], 'unlocatable')

    def test_no_site(self):
        # 起点压在信标上、步数为 0：唯一格点已被占用
        result = build_suggestion(10, [
            beacon('A', 2, 2, 3, 5),
            beacon('B', 8, 1, 4, 6),
            beacon('C', 6, 8, 3, 5),
        ], (2, 2), 0)
        self.assertEqual(result['status'], 'no_site')
        self.assertIn('reason', result)

    def test_recommendation_is_minimax(self):
        beacons = [
            beacon('A', 2, 2, 1, 4),
            beacon('B', 8, 3, 2, 5),
            beacon('C', 5, 9, 1, 5),
        ]
        origin, max_steps = (5, 5), 3
        result = build_suggestion(10, beacons, origin, max_steps)
        self.assertEqual(result['status'], 'recommended')

        cases = all_cases(solve(10, beacons))
        occupied = {(b['x'], b['y']) for b in beacons}
        feasible = [
            (x, y) for x in range(11) for y in range(11)
            if abs(x - origin[0]) + abs(y - origin[1]) <= max_steps
            and (x, y) not in occupied
        ]
        self.assertEqual(result['candidateCount'], len(feasible))

        # 逐一暴力核对：推荐点的最坏组数等于全局最小值
        expected_worst = min(brute_force_worst(cases, x, y) for x, y in feasible)
        rec = result['recommendation']
        self.assertEqual(rec['worstCases'], expected_worst)
        self.assertEqual(brute_force_worst(cases, rec['x'], rec['y']), expected_worst)

    def test_tie_break_steps_then_y_then_x(self):
        # 两个互斥假设各只有一个候选点：(0,0) 与 (5,0)。
        # 到两点距离平方不同的布点最坏组数都是 1，应选步数最少、再 y、x 最小者。
        beacons = [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 5, 0, 0, 0),
            beacon('C', 0, 5, 0, 10),
        ]
        origin, max_steps = (2, 0), 2
        result = build_suggestion(10, beacons, origin, max_steps)
        rec = result['recommendation']
        occupied = {(b['x'], b['y']) for b in beacons}
        feasible = [
            (x, y) for x in range(11) for y in range(11)
            if abs(x - origin[0]) + abs(y - origin[1]) <= max_steps
            and (x, y) not in occupied
        ]
        cases = all_cases(solve(10, beacons))
        optimal = {
            (x, y) for x, y in feasible
            if brute_force_worst(cases, x, y) == 1
        }
        expected = min(optimal,
                       key=lambda p: (abs(p[0] - origin[0]) + abs(p[1] - origin[1]),
                                      p[1], p[0]))
        self.assertEqual((rec['x'], rec['y']), expected)
        self.assertEqual(rec['steps'],
                         abs(rec['x'] - origin[0]) + abs(rec['y'] - origin[1]))

    def test_reading_groups_partition_cases(self):
        beacons = [
            beacon('A', 2, 2, 1, 4),
            beacon('B', 8, 3, 2, 5),
            beacon('C', 5, 9, 1, 5),
        ]
        result = build_suggestion(10, beacons, (5, 5), 3)
        rec = result['recommendation']

        grouped = sum(group['caseCount'] for group in rec['readings'])
        self.assertEqual(grouped, result['totalCases'])
        for group in rec['readings']:
            member_points = sum(len(m['points']) for m in group['members'])
            self.assertEqual(member_points, group['caseCount'])
            px, py = rec['x'], rec['y']
            for member in group['members']:
                for point in member['points']:
                    self.assertEqual(
                        (point['x'] - px) ** 2 + (point['y'] - py) ** 2,
                        group['reading'],
                    )

    def test_cases_are_disjoint_hypothesis_points(self):
        # 结构性质：全部读数无交点时，任意两个“排除一条读数”假设不可能
        # 共享候选点（共享点会同时满足全部读数，与前提矛盾）。因此
        # totalCases 恰为各假设候选点数之和，每个读数组只可能含唯一假设。
        beacons = [
            beacon('A', 0, 0, 0, 0),
            beacon('B', 5, 0, 0, 0),
            beacon('C', 0, 5, 0, 10),
        ]
        result = build_suggestion(10, beacons, (2, 0), 2)
        solved = solve(10, beacons)
        self.assertEqual(solved['status'], 'ambiguous_excluded')
        self.assertEqual(
            result['totalCases'],
            sum(h['pointCount'] for h in solved['hypotheses']),
        )
        seen = set()
        for hi, hypothesis in enumerate(solved['hypotheses']):
            for point in hypothesis_points(hypothesis):
                self.assertNotIn(point, seen)
                seen.add(point)
        for group in result['recommendation']['readings']:
            self.assertEqual(len(group['members']), 1)


if __name__ == '__main__':
    unittest.main()

import unittest

from app.locating import (
    allowed_points,
    solve,
    split_regions,
    to_int,
    validate_payload,
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


if __name__ == '__main__':
    unittest.main()

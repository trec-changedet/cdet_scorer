import unittest
from functools import partial

from cdet_scorer.measures import RecipRankPrime, RBPPrime, APPrime, NDCGPrime, RelLevel, RBO

class RecipRankPrimeTest(unittest.TestCase):
    def test_rr_prime(self):
        print('RR-prime -----')
        triples = [('', 0, partial(self.assertEqual, 1.0)),
                   ('00', 0, partial(self.assertAlmostEqual, 0.333, places=3)),
                   ('000', 0, partial(self.assertEqual, 0.25)),
                   ('111', 3, partial(self.assertEqual, 1.0)),
                   ('11', 3, partial(self.assertEqual, 1.0)),
                   ('11100', 3, partial(self.assertEqual, 1.0)),
                   ('101', 3, partial(self.assertEqual, 1.0)),
                   ('1', 3, partial(self.assertEqual, 1.0)),
                   ('10100', 3, partial(self.assertEqual, 1.0)),
                   ('011', 3, partial(self.assertEqual, 0.5)),
                   ('01001', 3, partial(self.assertEqual, 0.5))]
        for (r, nr, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            value = RecipRankPrime._recip_rank_prime(gains, nr)
            print(r, nr, '::', value)
            check(value)


class RBPPrimeTest(unittest.TestCase):
    def test_rbp_prime(self):
        print('RBP prime-----')
        triples = [('', [], partial(self.assertAlmostEqual, 1.0)),
                   ('00', [], partial(self.assertEqual, 0.25)),
                   ('000', [], partial(self.assertEqual, 0.125)),
                   ('111', [1,1,1], partial(self.assertEqual, 1.0)),
                   ('11', [1,1,1], partial(self.assertAlmostEqual, 0.917, places=3)),
                   ('11100', [1,1,1], partial(self.assertAlmostEqual, 0.906, places=3)),
                   ('101', [1,1,1], partial(self.assertAlmostEqual, 0.708, places=3)),
                   ('1', [1,1,1], partial(self.assertAlmostEqual, 0.667, places=3)),
                   ('10100', [1,1,1], partial(self.assertAlmostEqual, 0.646, places=3)),
                   ('011', [1,1,1], partial(self.assertAlmostEqual, 0.458, places=3)),
                   ('01001', [1,1,1], partial(self.assertAlmostEqual, 0.302, places=3))]
        for (r, all_gains, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            value = RBPPrime._rbp_prime(gains, 0.5, all_gains)
            print(r, all_gains, '::', value)
            check(value)

class APPrimeTest(unittest.TestCase):
    def test_ap_prime(self):
        print('AP prime-----')
        triples = [('', 0, partial(self.assertEqual, 1.0)),
                   ('00', 0, partial(self.assertAlmostEqual, 0.333, places=3)),
                   ('000', 0, partial(self.assertEqual, 0.25)),
                   ('111', 3, partial(self.assertEqual, 1.0)),
                   ('11', 3, partial(self.assertAlmostEqual, 0.648, places=3)),
                   ('11100', 3, partial(self.assertAlmostEqual, 0.917, places=3)),
                   ('101', 3, partial(self.assertAlmostEqual, 0.528, places=3)),
                   ('1', 3, partial(self.assertAlmostEqual, 0.306, places=3)),
                   ('10100', 3, partial(self.assertAlmostEqual, 0.491, places=3)),
                   ('011', 3, partial(self.assertAlmostEqual, 0.403, places=3)),
                   ('01001', 3, partial(self.assertAlmostEqual, 0.299, places=3))]
        for (r, num_rel, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            value = APPrime._ap_prime(gains, num_rel)
            print(r, num_rel, '::', value)
            check(value)

class NDCGTest(unittest.TestCase):
    def test_ndcg(self):
        print('NDCG-----')
        triples = [('323012', [3,3,3,2,2,2,1,0], partial(self.assertAlmostEqual, 0.785, places=3)),
                   ('213', [3,2,1], partial(self.assertAlmostEqual, 0.87, places=2)),
                   ('351', [5,3,1], partial(self.assertAlmostEqual, 0.90, places=2)),
                   ('153', [5,3,1], partial(self.assertAlmostEqual, 0.76, places=2))]
        for (r, all_gains, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            all_gains = [RelLevel(x) for x in all_gains]
            value = NDCGPrime._ndcg(gains, all_gains)
            print(r, all_gains, '::', value)
            check(value)

class NDCGPrimeTest(unittest.TestCase):
    def test_ndcg_prime(self):
        print('NDCG prime-----')
        triples = [('', 0, partial(self.assertEqual, 1.0)),
                   ('00', 0, partial(self.assertAlmostEqual, 0.500, places=3)),
                   ('000', 0, partial(self.assertAlmostEqual, 0.431, places=3)),
                   ('111', 3, partial(self.assertEqual, 1.0)),
                   ('11', 3, partial(self.assertAlmostEqual, 0.922, places=3)),
                   ('11100', 3, partial(self.assertAlmostEqual, 0.971, places=3)),
                   ('101', 3, partial(self.assertAlmostEqual, 0.698, places=3)),
                   ('1', 3, partial(self.assertAlmostEqual, 0.742, places=3)),
                   ('10100', 3, partial(self.assertAlmostEqual, 0.678, places=3)),
                   ('011', 3, partial(self.assertAlmostEqual, 0.554, places=3)),
                   ('01001', 3, partial(self.assertAlmostEqual, 0.490, places=3))]
        for (r, num_rel, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            all_gains = [RelLevel.AWARENESS for x in range(num_rel)]
            value = NDCGPrime._ndcg_prime(gains, all_gains)
            print(r, all_gains, '::', value)
            check(value)

    def test_ndcg_prime_ideal_capped_at_depth(self):
        '''NDCG' normalizes against DCGI@(d+1), the ideal of the system's own
        ranking length, not the full judgment pool. These cases have more
        relevant documents (num_rel) than the system retrieved (d), so the
        ideal must be truncated to d+1; normalizing against the whole pool
        would give much smaller values (e.g. 0.220 instead of 0.652).'''
        print('NDCG prime depth-capped ideal-----')
        triples = [('1', 10, partial(self.assertAlmostEqual, 0.652, places=3)),
                   ('11', 6, partial(self.assertAlmostEqual, 0.844, places=3)),
                   ('10', 5, partial(self.assertAlmostEqual, 0.516, places=3))]
        for (r, num_rel, check) in triples:
            gains = [RelLevel(int(x)) for x in list(r)]
            all_gains = [RelLevel.AWARENESS for x in range(num_rel)]
            value = NDCGPrime._ndcg_prime(gains, all_gains)
            print(r, num_rel, '::', value)
            check(value)


class RBOTest(unittest.TestCase):
    def test_rbo_identical(self):
        r = RBO(p=0.8)
        self.assertAlmostEqual(r.compute(['q1', 'q2', 'q3'], ['q1', 'q2', 'q3']), 1.0)
        self.assertAlmostEqual(r.compute([], []), 1.0)

    def test_rbo_disjoint(self):
        r = RBO(p=0.8)
        self.assertAlmostEqual(r.compute(['q1', 'q2'], ['q3', 'q4']), 0.0)
        self.assertAlmostEqual(r.compute([], ['q1']), 0.0)
        self.assertAlmostEqual(r.compute(['q1'], []), 0.0)

    def test_rbo_permutation(self):
        r = RBO(p=0.8)
        # S = [q1, q2], T = [q2, q1] -> (1-0.8)*(0*1 + 1*0.8) + (0.8^2)*1 = 0.16 + 0.64 = 0.80
        self.assertAlmostEqual(r.compute(['q1', 'q2'], ['q2', 'q1']), 0.8)

    
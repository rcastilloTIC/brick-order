"""Isolated simulator test: no Flask imports and no database dependency."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('order_simulator', Path(__file__).resolve().parents[1] / 'app/services/order_simulator.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SimulatorLimitsTests(unittest.TestCase):
    def test_scenarios(self):
        for seed in range(1, 31):
            for cutoff in (10, 35, 85, 110):
                with self.subTest(seed=seed, cutoff=cutoff):
                    base = module.build_demo(seed=seed, limits={'final_selection_limit': cutoff})
                    edit = module.build_demo(seed=seed, limits={'final_selection_limit': cutoff}, boost_ref=95, boost_units=120)
                    self.assertEqual(edit['selected_refs'], cutoff)
                    self.assertGreaterEqual(edit['intervention']['applied'], 0)
                    self.assertLessEqual(edit['intervention']['applied'], 120)
                    self.assertEqual(base['initial'] == edit['initial'], edit['intervention']['applied'] == 0)
                    self.assertEqual(len(edit['stages']), 8)

    def test_test_mode_limits(self):
        result = module.build_demo(limits={'phase_one_order_limit': 50, 'max_refs_phase_one': 3,
                                           'max_refs_phase_two': 6, 'final_selection_limit': 10})
        self.assertEqual(result['selected_refs'], 10)
        self.assertEqual(result['limits']['first_refs'], 3)
        self.assertEqual(result['limits']['second_refs'], 6)

    def test_rejects_invalid(self):
        for kwargs in ({'boost_ref': 111, 'boost_units': 10}, {'boost_ref': 0, 'boost_units': 1},
                       {'limits': {'final_selection_limit': 200}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                module.build_demo(**kwargs)

if __name__ == '__main__':
    unittest.main()

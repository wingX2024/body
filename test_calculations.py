import unittest

from calculations import (
    bmi,
    katch_mcardle_bmr,
    lean_body_mass,
    metabolic_age,
    mifflin_st_jeor_bmr,
    validate_measurement,
)


class CalculationTests(unittest.TestCase):
    def test_lean_mass_and_bmr(self):
        self.assertAlmostEqual(lean_body_mass(60, 25), 45)
        self.assertAlmostEqual(katch_mcardle_bmr(60, 25), 1342)

    def test_bmi(self):
        self.assertAlmostEqual(bmi(170, 65), 22.491, places=3)

    def test_metabolic_age_is_clamped(self):
        age, clamped = metabolic_age(230, 25, 70, "男性")
        self.assertEqual(age, 90)
        self.assertTrue(clamped)

    def test_mifflin_reference_decreases_with_age(self):
        at_30 = mifflin_st_jeor_bmr(30, 170, 65, "男性")
        at_40 = mifflin_st_jeor_bmr(40, 170, 65, "男性")
        self.assertEqual(at_30 - at_40, 50)

    def test_default_female_age_matches_reference_curve(self):
        age, clamped = metabolic_age(165, 60, 25, "女性")
        bmr = katch_mcardle_bmr(60, 25)
        self.assertAlmostEqual(age, 25.65, places=2)
        self.assertFalse(clamped)
        self.assertAlmostEqual(mifflin_st_jeor_bmr(age, 165, 60, "女性"), bmr)

    def test_default_male_age_matches_reference_curve(self):
        age, clamped = metabolic_age(165, 60, 25, "男性")
        bmr = katch_mcardle_bmr(60, 25)
        self.assertAlmostEqual(age, 58.85, places=2)
        self.assertFalse(clamped)
        self.assertAlmostEqual(mifflin_st_jeor_bmr(age, 165, 60, "男性"), bmr)

    def test_validation(self):
        self.assertEqual(validate_measurement(165, 60, 25, 8, 2.5), [])
        self.assertTrue(validate_measurement(99, 60, 25, 8, 2.5))


if __name__ == "__main__":
    unittest.main()
